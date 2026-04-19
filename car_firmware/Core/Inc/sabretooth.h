//
// Created by ashhar on 19/04/2026.
//

#ifndef CAR_FIRMWARE_SABRETOOTH_H
#define CAR_FIRMWARE_SABRETOOTH_H
#include <stdint.h>

typedef struct motor_pack_s {
    uint8_t add;
    uint8_t cmd;
    uint8_t data;
    uint8_t check;
}motor_pack_t;

typedef enum {
    FORWARD = 0,
    BACKWARD = 1
} motor_direction_t;

typedef enum {
    MOTOR_A = 0,
    MOTOR_B = 4
} motor_select_t;

void motor_set_maxV(motor_pack_t* motor, uint8_t v);
void motor_set_minV(motor_pack_t* motor, uint8_t v);
void motor_check(motor_pack_t* motor);
void motor_drive(motor_pack_t* motor, motor_select_t motor_select, motor_direction_t direction, uint8_t speed);

#endif //CAR_FIRMWARE_SABRETOOTH_H