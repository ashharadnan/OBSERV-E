//
// Created by ashhar on 18/11/2025.
//

#include "servo_helper.h"

/* Private Methdods */
static void drive_servo(servo_t* servo,  float drive_angle) {
    servo->width = WIDTH(drive_angle);
    *(servo->timCCR) = (uint32_t)(servo->width * (APB1_CLK/1000.0)) - 1;
}

/* Public Methods */
void SERVO_Init(servo_t* servo, uint32_t* CCR, servo_polarity_t polarity) {
    servo->pulse = 0;
    servo->width = WIDTH(0);
    servo->timCCR = CCR;
    servo->polarity = polarity;
}

void SERVO_setpulse(servo_t* servo, float pulse) {
    if (-0.6>pulse) {
        pulse = -0.6;
    }
    else if (0.6<pulse) {
        pulse = 0.6;
    }
    servo->pulse = pulse;
    drive_servo(servo, (float)(servo->polarity)*pulse);
}

