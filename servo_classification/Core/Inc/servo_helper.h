//
// Created by ashhar on 18/11/2025.
//

#ifndef SERVO_HELPER_H
#define SERVO_HELPER_H

/* Includes */
// MCU dependant header
#include "stm32f4xx_hal.h"

/* Macros */
// Depends on the peripheral clock of the Timer
#define APB1_CLK 16000000UL
// Different for each servo, this value is just a regressed version of all the servos connected to the system0
#define WIDTH(pulse) (pulse + 1.5) //GoBilda

/* Type Definitions */
typedef enum{
    SERVO_POLARITY_NEG = -1,
    SERVO_POLARITY_POS = 1,
}servo_polarity_t;

typedef struct {
    float pulse;
    float width;
    uint32_t* timCCR;
    servo_polarity_t polarity;
}servo_t;

/* Exported Methods */
void SERVO_Init(servo_t* servo, uint32_t* CCR, servo_polarity_t polarity);
void SERVO_setpulse(servo_t* servo, float pulse);

#endif //SERVO_HELPER_H