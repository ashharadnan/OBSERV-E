#include <sh2_hal.h>
#include <sh2_err.h>
#include <stdbool.h>
#include <string.h>
#include <sys/types.h>

/* Private Defines */
#define SH2_BPS (3000000)            // always 3Mbps
// Time between transmitted characters
// Explanation: 1000000.0 : 1 million microseconds per second
//              10.0      : 10 bit times per character
#define TX_CHAR_US ((1000000.0 * 10.0/SH2_BPS))  // time for one char to clock out
#define TX_INTERVAL_US ((TX_CHAR_US >= 100.0) ? (unsigned)(TX_CHAR_US*1.2) : 100)

#define RESET_DELAY_US (10000)
#define START_DELAY_US (4000000)

#define RFC1662_FLAG (0x7E)
#define RFC1662_ESC (0x7D)

#define PROTOCOL_CONTROL (0)
#define PROTOCOL_SHTP (1)

#define DMA_SIZE (64)


/* Private Types */
typedef enum {
    OUTSIDE_FRAME,   // Waiting for start of frame
    INSIDE_FRAME,    // Inside frame until end of frame
    ESCAPED,         // Inside frame, after escape char
} RxState_t;

typedef enum {
    TX_IDLE,
    TX_SENDING_BSQ,
    TX_SENDING_FRAME,
} TxState_t;

/* Private Variables */
static sh2_Hal_t sh2_Hal;

// Hardware Devices
// GPIOs
static GPIO_TypeDef* sh2_rstn_GPIO_Port; static uint16_t sh2_rstn_Pin;
static GPIO_TypeDef* sh2_intn_GPIO_Port; static uint16_t sh2_intn_Pin; static IRQn_Type sh2_int_irqn;

// UART
static UART_HandleTypeDef* sh2_uart; static IRQn_Type sh2_uart_irqn;
static DMA_HandleTypeDef* sh2_dma_rx; static IRQn_Type sh2_dma_rx_irqn;

// Rx Support
static volatile uint8_t rxBuf[DMA_SIZE] = {0};
static uint32_t rxIx = 0;
static uint32_t rxTimestamp_uS;

// RFC 1622 frame decode
static uint8_t rxFrame[SH2_HAL_MAX_TRANSFER_IN];
static uint32_t rxFrameLen;
static bool rxFrameReady;
static RxState_t rxState;

// Tx Support
static uint32_t lastTxTime = 0;
static uint16_t lastBsn = 0;
static volatile TxState_t txState = TX_IDLE;
static uint8_t txFrame[2*SH2_HAL_MAX_TRANSFER_OUT+2];
static uint32_t txFrameLen;
static uint32_t txIx = 0;

// BSQ (encoded)
static const uint8_t bsq[3] = { RFC1662_FLAG, PROTOCOL_CONTROL, RFC1662_FLAG};

// Functional
static bool isOpen = false;
static bool inReset;
volatile bool usartErrorEncountered = false;
volatile bool usartStreaming = false;


/* Private Methods */
static void enableInterrupts(void) {
    HAL_NVIC_EnableIRQ(sh2_int_irqn);
    HAL_NVIC_EnableIRQ(sh2_uart_irqn);
    HAL_NVIC_EnableIRQ(sh2_dma_rx_irqn);
}

static void disableInterrupts(void) {
    HAL_NVIC_DisableIRQ(sh2_int_irqn);
    HAL_NVIC_DisableIRQ(sh2_uart_irqn);
    HAL_NVIC_DisableIRQ(sh2_dma_rx_irqn);
}

static void rst(bool state) {
    HAL_GPIO_WritePin(sh2_rstn_GPIO_Port, sh2_rstn_Pin, !state);
}

// reset RFC 1662 decode state machine
static void rfc1662_reset(void)
{
    rxFrameLen = 0;
    rxFrameReady = false;
    rxState = OUTSIDE_FRAME;
}

static void rxResetFrame(void)
{
    rxFrameLen = 0;
    rxFrameReady = false;
}

static void rxAddToFrame(uint8_t c)
{
    // Add the character to the frame in progress
    if (rxFrameLen < sizeof(rxFrame)) {
        rxFrame[rxFrameLen] = c;
        rxFrameLen++;
    }
    else {
        // overflowed the buffer!  Don't store data
        rxFrameLen++;
    }
}

// Process a received byte through RFC 1662 framing
static void rfc1662_rx(uint8_t c)
{
    // Use state machine to build up chars into frames for delivery.
    switch (rxState) {
        case OUTSIDE_FRAME:
            // Look for start of frame
            if (c == RFC1662_FLAG) {
                // Init frame in progress
                rxResetFrame();
                rxState = INSIDE_FRAME;
            }
            break;
        case INSIDE_FRAME:
            // Look for end of frame
            if (c == RFC1662_FLAG) {
                if (rxFrameLen > 0) {
                    // Frame is done
                    rxFrameReady = true;
                    rxState = OUTSIDE_FRAME;
                }
                else {
                    // Treat second consec flag as another start flag.
                    rxState = INSIDE_FRAME;
                }
            }
            else if (c == RFC1662_ESC) {
                // Go to escaped state so next char can be a flag or escape
                rxState = ESCAPED;
            }
            else {
                rxAddToFrame(c);
            }
            break;
        case ESCAPED:
            rxAddToFrame(c ^ 0x20);
            rxState = INSIDE_FRAME;
            break;
        default:
            // Bad state.  Recover by resetting to outside frame state
            rxState = OUTSIDE_FRAME;
            break;
    }
}

static void delay_us(uint32_t t) {
    uint32_t start = TimeNowUs();
    while ((TimeNowUs() - start) < t);
}

static void reset_delay_us(uint32_t t) {
    uint32_t start = TimeNowUs();
    while (((TimeNowUs() - start) < t) && inReset);
}

// Called from write and from read to move transmit processing forward.
static void txStep(void)
{
    // Inactive, return quickly
    if (txState == TX_IDLE) return;

    // Not enough time elapsed since last transmit, skip this
    uint32_t now = TimeNowUs();
    if ((now - lastTxTime) < TX_INTERVAL_US) return;

    // We have stuff to do and it's time to do it.
    if (txState == TX_SENDING_BSQ) {
        if ((txIx == 0) && (lastBsn >= txFrameLen)) {
            // Switch to sending frame
            txState = TX_SENDING_FRAME;
        }
        else {
            // Send one byte of BSQ
            HAL_UART_Transmit_IT(sh2_uart, (uint8_t *)&bsq[txIx], 1);
            txIx = (txIx + 1) % sizeof(bsq);
            lastTxTime = now;
        }
    }
    if (txState == TX_SENDING_FRAME) {
        if (txIx >= txFrameLen) {
            // Frame transmit is done
            txIx = 0;
            txState = TX_IDLE;
            lastBsn = 0;
        }
        else {
            // Send one byte
            HAL_UART_Transmit_IT(sh2_uart, &txFrame[txIx], 1);
            txIx += 1;
            lastTxTime = now;
        }
    }
}

static void txStore(uint8_t c)
{
    if (txFrameLen < sizeof(txFrame)) {
        txFrame[txFrameLen] = c;
    }
    txFrameLen++;
}

// Form transmit buffer with flags, PROTOCOL_SHTP id, RFC 1662 encoding.
// Result ends up in txFrame, txFrameLen.
// If the process overflows, txFrameLen will be > sizeof(txFrame)
// but the extra bytes will not be written beyond txFrame[]
static void txEncode(uint8_t *pSrc, uint32_t len)
{
    uint32_t i = 0;
    txFrameLen = 0;

    // Start of frame
    txStore(RFC1662_FLAG);

    // Protocol ID
    txStore(PROTOCOL_SHTP);

    // Frame contents
    for (i = 0; i < len; i++) {
        if ((pSrc[i] == RFC1662_FLAG) ||
            (pSrc[i] == RFC1662_ESC)) {
            // Store escaped character
            txStore(RFC1662_ESC);
            txStore(pSrc[i] ^ 0x20);
            }
        else {
            // store the character normally
            txStore(pSrc[i]);
        }
    }

    // End of frame
    txStore(RFC1662_FLAG);
}

/* SH2 HAL Methods */
static int sh2_hal_open(sh2_Hal_t *self) {
    if (isOpen) return SH2_ERR;

    isOpen = true;

    // Reset sensor
    rst(true);
    inReset = true;
    disableInterrupts();
    delay_us(RESET_DELAY_US);
    rfc1662_reset();
    lastBsn = 0;
    enableInterrupts();

    // Start data flow
    HAL_UART_Receive_DMA(sh2_uart, rxBuf, sizeof(rxBuf));
    usartStreaming = true;
    rst(false);

    // Wait for Interrupt
    reset_delay_us(START_DELAY_US);
}


static void sh2_hal_close(sh2_Hal_t *self) {
    disableInterrupts();

    // Reset sensor
    rst(true);
    inReset = true;
    isOpen = false;
}


static int sh2_hal_read(sh2_Hal_t *self, uint8_t *pBuffer, unsigned len, uint32_t *t) {
    uint32_t stopPoint = sizeof(rxBuf)-__HAL_DMA_GET_COUNTER(sh2_dma_rx);
    int retval = 0;

    // This function needs to:
    //  * Process data from DMA buffer, through frame assembly.
    //  * Store data from BSN frames for Tx side.
    //  * Keep tx data flowing (at 1 char per 100uS.)
    //  * Deliver a whole frame to caller, if one is ready

    // If UART encountered an error, get data flowing again.
    if (usartErrorEncountered) {
        usartErrorEncountered = false;
        // reset receiver state
        rxIx = 0;
        rfc1662_reset();
        // restart DMA process
        HAL_UART_Receive_DMA(sh2_uart, rxBuf, sizeof(rxBuf));
    }

    while ((rxIx != stopPoint) && !rxFrameReady) {
        rfc1662_rx(rxBuf[rxIx]);
        rxIx = (rxIx+1) & sizeof(rxBuf)-1;

        if (rxFrameReady && (rxFrameLen > 0) && (rxFrame[0] == PROTOCOL_CONTROL)) {
            // Process control protocol (BSN received)
            lastBsn = (rxFrame[2]<<8) + rxFrame[1];

            // That frame was consumed
            rxFrameReady = false;
        }
    }

    // Try to move the tx process forward by sending a character, if possible.
    txStep();

    // If a frame was assembled, return it
    if (rxFrameReady) {
        if (rxFrameLen <= sizeof(rxFrame)) {
            // Set timestamp when returning a frame
            *t = rxTimestamp_uS;

            // Copy into pBuffer
            memcpy(pBuffer, &rxFrame[1], rxFrameLen-1);  // Copy all but first char, protocol id

            // signal that we consumed the frame
            retval = rxFrameLen-1;
        }
        else {
            // Frame overflowed rxFrame buffer and was discarded
        }
        rxFrameReady = false;
    }

    return retval;
}


static int sh2_hal_write(sh2_Hal_t *self, uint8_t *pBuffer, unsigned len) {
    // Validate parameters
    if ((pBuffer == 0) || (len == 0)) {
        return SH2_ERR_BAD_PARAM;
    }

    // If write mechanisms are busy, return 0.  Try again later.
    if (txState != TX_IDLE) {
        return 0;
    }

    // RFC encode the buffer and store in txFrame
    txEncode(pBuffer, len);
    if (txFrameLen > sizeof(txFrame)) {
        // frame overflowed the buffer after encode
        return SH2_ERR_BAD_PARAM;
    }

    // Reset txIndex
    txIx = 0;

    // Tx process will start with buffer status query.
    txState = TX_SENDING_BSQ;

    // Try to move the tx process forward by sending a character, if possible.
    txStep();

    return len;
}


static uint32_t sh2_hal_getTimeUs(sh2_Hal_t *self)
{
    return TimeNowUs();
}


/* Public Functions and Methods */
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart == sh2_uart) usartErrorEncountered = true;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef* huart) {
    if (huart == sh2_uart);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin) {
    if (GPIO_Pin == sh2_intn_Pin) {
        inReset = false;
        rxTimestamp_uS = TimeNowUs();
    }
}

sh2_Hal_t* sh2_HAL_init(
    GPIO_TypeDef* rstn_port, uint16_t rstn_pin,
    GPIO_TypeDef* intn_port, uint16_t intn_pin, IRQn_Type intn_irqn,
    UART_HandleTypeDef* huart, IRQn_Type huart_irqn,
    DMA_HandleTypeDef* dma_rx, IRQn_Type dma_rx_irqn
    ) {

    sh2_rstn_GPIO_Port = rstn_port; sh2_rstn_Pin = rstn_pin;
    sh2_intn_GPIO_Port = intn_port; sh2_intn_Pin = intn_pin; sh2_int_irqn = intn_irqn;

    sh2_uart = huart; sh2_uart_irqn = huart_irqn;
    sh2_dma_rx = dma_rx; sh2_dma_rx_irqn = dma_rx_irqn;

    sh2_Hal.open = sh2_hal_open;
    sh2_Hal.close = sh2_hal_close;
    sh2_Hal.read = sh2_hal_read;
    sh2_Hal.write = sh2_hal_write;
    sh2_Hal.getTimeUs = sh2_hal_getTimeUs;

    return &sh2_Hal;
}