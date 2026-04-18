//
// Created by ashha on 08/04/2026.
//

#include "control_loop.h"
#include "usbd_cdc_if.h"


/* Private Variables */
static uint8_t msg[1024];
static uint32_t lastTimestamp = 0;

void control_loop() {
    // Print characteristics
    if (lastTimestamp != pimu_data->timestamp_ms) {
        HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, 1);
        lastTimestamp = pimu_data->timestamp_ms;
        //CDC_Transmit_FS((uint8_t*)&PACK, sizeof(PACK));
        memset(msg, 0x00, sizeof(msg));
        snprintf(msg, sizeof(msg), "%lu ms\t\t%.2f\t\t%.2f\t\t%.2f\t\t%.2f\t\t%.2f rad/s\t\t%.2f rad/s\t\t%.2f rad/s\r\n",
          pimu_data->timestamp_ms, pimu_data->r, pimu_data->i, pimu_data->j, pimu_data->k,
          pimu_data->velX, pimu_data->velY, pimu_data->velZ);
        CDC_Transmit_FS(msg, sizeof(msg));
        HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, 0);
    }
}