/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    App/custom_app.c
  * @author  MCD Application Team
  * @brief   Custom Example Application (Server)
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "app_common.h"
#include "dbg_trace.h"
#include "ble.h"
#include "custom_app.h"
#include "custom_stm.h"
#include "stm32_seq.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdbool.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
typedef struct
{
  /* MOTOR1_SVC */
  /* MOTOR2_SVC */
  /* MOTOR3_SVC */
  /* MOTOR4_SVC */
  /* Voltage_SVC */
  /* USER CODE BEGIN CUSTOM_APP_Context_t */

  /* USER CODE END CUSTOM_APP_Context_t */

  uint16_t              ConnectionHandle;
} Custom_App_Context_t;

/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private defines ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macros -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
/**
 * START of Section BLE_APP_CONTEXT
 */

static Custom_App_Context_t Custom_App_Context;

/**
 * END of Section BLE_APP_CONTEXT
 */

uint8_t UpdateCharData[512];
uint8_t NotifyCharData[512];
uint16_t Connection_Handle;
/* USER CODE BEGIN PV */
bool flags[4] = {false};
int8_t inputs[4] = {0};

motor_pack_t* motors[4] = {&motor1A
,&motor1B
,&motor2A
,&motor2B};

UART_HandleTypeDef* ports[4] = {
  &huart1,
  &huart1,
  &hlpuart1,
  &hlpuart1
};
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
/* MOTOR1_SVC */
/* MOTOR2_SVC */
/* MOTOR3_SVC */
/* MOTOR4_SVC */
/* Voltage_SVC */

/* USER CODE BEGIN PFP */
void Drive_Task(void);
/* USER CODE END PFP */

/* Functions Definition ------------------------------------------------------*/
void Custom_STM_App_Notification(Custom_STM_App_Notification_evt_t *pNotification)
{
  /* USER CODE BEGIN CUSTOM_STM_App_Notification_1 */

  /* USER CODE END CUSTOM_STM_App_Notification_1 */
  switch (pNotification->Custom_Evt_Opcode)
  {
    /* USER CODE BEGIN CUSTOM_STM_App_Notification_Custom_Evt_Opcode */

    /* USER CODE END CUSTOM_STM_App_Notification_Custom_Evt_Opcode */

    /* MOTOR1_SVC */
    case CUSTOM_STM_P1_READ_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P1_READ_EVT */

      /* USER CODE END CUSTOM_STM_P1_READ_EVT */
      break;

    case CUSTOM_STM_P1_WRITE_NO_RESP_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P1_WRITE_NO_RESP_EVT */
      if(pNotification->DataTransfered.Length > 0)
      {
        // Assuming a 1-byte characteristic. Adjust index for larger data types.
        inputs[0] = pNotification->DataTransfered.pPayload[0];
        flags[0] = true;
      }
      /* USER CODE END CUSTOM_STM_P1_WRITE_NO_RESP_EVT */
      break;

    /* MOTOR2_SVC */
    case CUSTOM_STM_P2_READ_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P2_READ_EVT */

      /* USER CODE END CUSTOM_STM_P2_READ_EVT */
      break;

    case CUSTOM_STM_P2_WRITE_NO_RESP_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P2_WRITE_NO_RESP_EVT */
      if(pNotification->DataTransfered.Length > 0)
      {
        // Assuming a 1-byte characteristic. Adjust index for larger data types.
        inputs[1] = pNotification->DataTransfered.pPayload[0];
        flags[1] = true;
      }
      /* USER CODE END CUSTOM_STM_P2_WRITE_NO_RESP_EVT */
      break;

    /* MOTOR3_SVC */
    case CUSTOM_STM_P3_READ_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P3_READ_EVT */

      /* USER CODE END CUSTOM_STM_P3_READ_EVT */
      break;

    case CUSTOM_STM_P3_WRITE_NO_RESP_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P3_WRITE_NO_RESP_EVT */
      if(pNotification->DataTransfered.Length > 0)
      {
        // Assuming a 1-byte characteristic. Adjust index for larger data types.
        inputs[02] = pNotification->DataTransfered.pPayload[0];
        flags[02] = true;
      }
      /* USER CODE END CUSTOM_STM_P3_WRITE_NO_RESP_EVT */
      break;

    /* MOTOR4_SVC */
    case CUSTOM_STM_P4_READ_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P4_READ_EVT */

      /* USER CODE END CUSTOM_STM_P4_READ_EVT */
      break;

    case CUSTOM_STM_P4_WRITE_NO_RESP_EVT:
      /* USER CODE BEGIN CUSTOM_STM_P4_WRITE_NO_RESP_EVT */
      if(pNotification->DataTransfered.Length > 0)
      {
        // Assuming a 1-byte characteristic. Adjust index for larger data types.
        inputs[03] = pNotification->DataTransfered.pPayload[0];
        flags[03] = true;
      }
      /* USER CODE END CUSTOM_STM_P4_WRITE_NO_RESP_EVT */
      break;

    /* Voltage_SVC */
    case CUSTOM_STM_V_READ_READ_EVT:
      /* USER CODE BEGIN CUSTOM_STM_V_READ_READ_EVT */

      /* USER CODE END CUSTOM_STM_V_READ_READ_EVT */
      break;

    case CUSTOM_STM_NOTIFICATION_COMPLETE_EVT:
      /* USER CODE BEGIN CUSTOM_STM_NOTIFICATION_COMPLETE_EVT */

      /* USER CODE END CUSTOM_STM_NOTIFICATION_COMPLETE_EVT */
      break;

    default:
      /* USER CODE BEGIN CUSTOM_STM_App_Notification_default */

      /* USER CODE END CUSTOM_STM_App_Notification_default */
      break;
  }
  /* USER CODE BEGIN CUSTOM_STM_App_Notification_2 */

  /* USER CODE END CUSTOM_STM_App_Notification_2 */
  return;
}

void Custom_APP_Notification(Custom_App_ConnHandle_Not_evt_t *pNotification)
{
  /* USER CODE BEGIN CUSTOM_APP_Notification_1 */

  /* USER CODE END CUSTOM_APP_Notification_1 */

  switch (pNotification->Custom_Evt_Opcode)
  {
    /* USER CODE BEGIN CUSTOM_APP_Notification_Custom_Evt_Opcode */

    /* USER CODE END P2PS_CUSTOM_Notification_Custom_Evt_Opcode */
    case CUSTOM_CONN_HANDLE_EVT :
      /* USER CODE BEGIN CUSTOM_CONN_HANDLE_EVT */

      /* USER CODE END CUSTOM_CONN_HANDLE_EVT */
      break;

    case CUSTOM_DISCON_HANDLE_EVT :
      /* USER CODE BEGIN CUSTOM_DISCON_HANDLE_EVT */

      /* USER CODE END CUSTOM_DISCON_HANDLE_EVT */
      break;

    default:
      /* USER CODE BEGIN CUSTOM_APP_Notification_default */

      /* USER CODE END CUSTOM_APP_Notification_default */
      break;
  }

  /* USER CODE BEGIN CUSTOM_APP_Notification_2 */

  /* USER CODE END CUSTOM_APP_Notification_2 */

  return;
}

void Custom_APP_Init(void)
{
  /* USER CODE BEGIN CUSTOM_APP_Init */
  UTIL_SEQ_RegTask(1<<CFG_DRIVE_TASK, UTIL_SEQ_RFU, Drive_Task);
  UTIL_SEQ_SetTask(1<<CFG_DRIVE_TASK, CFG_SCH_PRIO_0);
  /* USER CODE END CUSTOM_APP_Init */
  return;
}

/* USER CODE BEGIN FD */
void Drive_Task(void) {

  for (int i = 0; i < 4; i++) {
    if (flags[i]) {
      flags[i]=false;
      if (inputs[i] < 0){
        motor_drive(motors[i], (i%2)*4, BACKWARD, inputs[i]*-1);
      }
      else {
        motor_drive(motors[i], (i%2)*4, FORWARD, inputs[i]);
      }
      motor_check(motors[i]);
      HAL_UART_Transmit(ports[i], (uint8_t*)motors[i], 4,HAL_MAX_DELAY);
      HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
    }
  }

  UTIL_SEQ_SetTask(1<<CFG_DRIVE_TASK, CFG_SCH_PRIO_0);
}
/* USER CODE END FD */

/*************************************************************
 *
 * LOCAL FUNCTIONS
 *
 *************************************************************/

/* MOTOR1_SVC */
/* MOTOR2_SVC */
/* MOTOR3_SVC */
/* MOTOR4_SVC */
/* Voltage_SVC */

/* USER CODE BEGIN FD_LOCAL_FUNCTIONS*/

/* USER CODE END FD_LOCAL_FUNCTIONS*/
