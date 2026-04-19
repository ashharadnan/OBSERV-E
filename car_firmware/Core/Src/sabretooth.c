//
// Created by ashhar on 19/04/2026.
//

#include "sabretooth.h"

void motor_check(motor_pack_t* motor) {
    motor->check = (motor->add + motor->cmd + motor->data) & 0b01111111;
}

void motor_drive(motor_pack_t* motor, motor_select_t motor_select, motor_direction_t direction, uint8_t speed) {
    motor->cmd = motor_select+direction;
    motor->data = speed;
}

void motor_set_maxV(motor_pack_t* motor, uint8_t v) {
    motor->cmd = 3;
    motor->data = v*5.12;
}

void motor_set_minV(motor_pack_t* motor, uint8_t v) {
    motor->cmd = 2;
    motor->data = (v-6)*5;
}