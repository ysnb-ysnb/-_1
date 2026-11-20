/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
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

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef struct
{
  GPIO_TypeDef *in1_port;
  uint16_t in1_pin;
  GPIO_TypeDef *in2_port;
  uint16_t in2_pin;
  uint32_t pwm_channel;
  int16_t trim_percent;
  uint8_t inverted;
  int16_t current_pwm;
} MotorConfig_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define PWM_MAX_VALUE          399
#define PWM_MIN_RUN            60
#define PWM_RAMP_STEP          25
#define CONTROL_PERIOD_MS      10U
#define MOTION_TIMEOUT_MS      1200U
#define DEFAULT_SPEED_PERCENT  35U
#define MIN_SPEED_PERCENT      20U
#define MAX_SPEED_PERCENT      100U
#define SPEED_STEP_PERCENT     10U
#define VECTOR_BUFFER_SIZE     28U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
TIM_HandleTypeDef htim4;

UART_HandleTypeDef huart1;

/* USER CODE BEGIN PV */
static MotorConfig_t motors[4] =
{
  /* Order must match wheel[] in set_motion: FL, FR, RL, RR. */
  {GPIOB, GPIO_PIN_12, GPIOB, GPIO_PIN_13, TIM_CHANNEL_1, 100, 0, 0},
  {GPIOA, GPIO_PIN_0,  GPIOA, GPIO_PIN_1,  TIM_CHANNEL_3, 100, 0, 0},
  {GPIOB, GPIO_PIN_14, GPIOB, GPIO_PIN_15, TIM_CHANNEL_2, 100, 0, 0},
  {GPIOA, GPIO_PIN_2,  GPIOA, GPIO_PIN_3,  TIM_CHANNEL_4, 100, 0, 0}
};

static int16_t target_pwm[4];
static int16_t motion_vx;
static int16_t motion_vy;
static int16_t motion_wz;
static uint8_t motion_active;
static uint32_t motion_deadline;
static uint8_t speed_percent = DEFAULT_SPEED_PERCENT;
static uint32_t last_control_tick;

static uint8_t vector_collecting;
static uint8_t vector_length;
static char vector_buffer[VECTOR_BUFFER_SIZE];
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_TIM4_Init(void);
static void MX_USART1_UART_Init(void);
/* USER CODE BEGIN PFP */
static void uart_puts(const char *text);
static int32_t abs_i32(int32_t value);
static void motors_hard_stop(void);
static void motor_output(MotorConfig_t *motor, int16_t pwm);
static void motors_ramp(void);
static void set_motion(int16_t vx, int16_t vy, int16_t wz);
static void start_motion(int16_t vx, int16_t vy, int16_t wz);
static void process_command(uint8_t byte);
static void process_vector(void);
static uint8_t parse_int16(const char **cursor, int16_t *value);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  uint8_t rx_byte = 0;
  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_TIM4_Init();
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_2);
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_3);
  HAL_TIM_PWM_Start(&htim4, TIM_CHANNEL_4);
  motors_hard_stop();
  last_control_tick = HAL_GetTick();

  uart_puts("MECANUM X READY\r\n");
  uart_puts("F/B/L/R=move Q/E=rotate S=stop\r\n");
  uart_puts("G/I/H/J=diagonal +=speed -=speed\r\n");
  uart_puts("V,fwd,right,ccw<ENTER>=vector -100..100\r\n");
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    if (HAL_UART_Receive(&huart1, &rx_byte, 1, 2) == HAL_OK)
    {
      process_command(rx_byte);
    }

    if ((HAL_GetTick() - last_control_tick) >= CONTROL_PERIOD_MS)
    {
      last_control_tick = HAL_GetTick();
      motors_ramp();
    }

    if (motion_active &&
        ((int32_t)(HAL_GetTick() - motion_deadline) >= 0))
    {
      motion_active = 0;
      motion_vx = 0;
      motion_vy = 0;
      motion_wz = 0;
      set_motion(0, 0, 0);
      uart_puts("STOP timeout\r\n");
    }

    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief TIM4 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM4_Init(void)
{

  /* USER CODE BEGIN TIM4_Init 0 */

  /* USER CODE END TIM4_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM4_Init 1 */

  /* USER CODE END TIM4_Init 1 */
  htim4.Instance = TIM4;
  htim4.Init.Prescaler = 0;
  htim4.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim4.Init.Period = 399;
  htim4.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim4.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_Base_Init(&htim4) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim4, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim4) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim4, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_3) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim4, &sConfigOC, TIM_CHANNEL_4) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM4_Init 2 */

  /* USER CODE END TIM4_Init 2 */
  HAL_TIM_MspPostInit(&htim4);

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 9600;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, GPIO_PIN_12|GPIO_PIN_13|GPIO_PIN_14|GPIO_PIN_15, GPIO_PIN_RESET);

  /*Configure GPIO pins : PA0 PA1 PA2 PA3 */
  GPIO_InitStruct.Pin = GPIO_PIN_0|GPIO_PIN_1|GPIO_PIN_2|GPIO_PIN_3;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pins : PB12 PB13 PB14 PB15 */
  GPIO_InitStruct.Pin = GPIO_PIN_12|GPIO_PIN_13|GPIO_PIN_14|GPIO_PIN_15;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
static void uart_puts(const char *text)
{
  HAL_UART_Transmit(&huart1,
                    (const uint8_t *)text,
                    (uint16_t)strlen(text),
                    HAL_MAX_DELAY);
}

static int32_t abs_i32(int32_t value)
{
  return (value < 0) ? -value : value;
}

static void motor_output(MotorConfig_t *motor, int16_t pwm)
{
  uint8_t forward;
  uint16_t compare;

  if (pwm == 0)
  {
    __HAL_TIM_SET_COMPARE(&htim4, motor->pwm_channel, 0);
    HAL_GPIO_WritePin(motor->in1_port, motor->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(motor->in2_port, motor->in2_pin, GPIO_PIN_RESET);
    return;
  }

  forward = (pwm > 0) ? 1U : 0U;
  if (motor->inverted != 0U)
  {
    forward = !forward;
  }

  if (forward != 0U)
  {
    HAL_GPIO_WritePin(motor->in1_port, motor->in1_pin, GPIO_PIN_SET);
    HAL_GPIO_WritePin(motor->in2_port, motor->in2_pin, GPIO_PIN_RESET);
  }
  else
  {
    HAL_GPIO_WritePin(motor->in1_port, motor->in1_pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(motor->in2_port, motor->in2_pin, GPIO_PIN_SET);
  }

  compare = (uint16_t)abs_i32(pwm);
  if (compare > PWM_MAX_VALUE)
  {
    compare = PWM_MAX_VALUE;
  }
  __HAL_TIM_SET_COMPARE(&htim4, motor->pwm_channel, compare);
}

static void motors_hard_stop(void)
{
  uint8_t index;

  for (index = 0U; index < 4U; index++)
  {
    motors[index].current_pwm = 0;
    target_pwm[index] = 0;
    motor_output(&motors[index], 0);
  }
}

static void motors_ramp(void)
{
  uint8_t index;
  int16_t current;
  int16_t target;

  for (index = 0U; index < 4U; index++)
  {
    current = motors[index].current_pwm;
    target = target_pwm[index];

    if (((current < 0) && (target > 0)) ||
        ((current > 0) && (target < 0)))
    {
      if (abs_i32(current) <= PWM_RAMP_STEP)
      {
        current = 0;
      }
      else
      {
        current += (current > 0) ? -PWM_RAMP_STEP : PWM_RAMP_STEP;
      }
    }
    else if (current < target)
    {
      current = (int16_t)((target - current > PWM_RAMP_STEP)
                          ? current + PWM_RAMP_STEP : target);
    }
    else if (current > target)
    {
      current = (int16_t)((current - target > PWM_RAMP_STEP)
                          ? current - PWM_RAMP_STEP : target);
    }

    if (current != motors[index].current_pwm)
    {
      motors[index].current_pwm = current;
      motor_output(&motors[index], current);
    }
  }
}

static void set_motion(int16_t vx, int16_t vy, int16_t wz)
{
  int32_t wheel[4];
  int32_t max_wheel = 0;
  int32_t speed;
  uint8_t index;

  motion_vx = vx;
  motion_vy = vy;
  motion_wz = wz;

  vx = (int16_t)((int32_t)vx * speed_percent / 100);
  vy = (int16_t)((int32_t)vy * speed_percent / 100);
  wz = (int16_t)((int32_t)wz * speed_percent / 100);

  /*
   * Standard X mecanum layout:
   * FL = forward + right - CCW
   * FR = forward - right + CCW
   * RL = forward - right - CCW
   * RR = forward + right + CCW
   */
  wheel[0] = (int32_t)vx + vy - wz;
  wheel[1] = (int32_t)vx - vy + wz;
  wheel[2] = (int32_t)vx - vy - wz;
  wheel[3] = (int32_t)vx + vy + wz;

  for (index = 0U; index < 4U; index++)
  {
    if (abs_i32(wheel[index]) > max_wheel)
    {
      max_wheel = abs_i32(wheel[index]);
    }
  }

  if (max_wheel > 100)
  {
    for (index = 0U; index < 4U; index++)
    {
      wheel[index] = wheel[index] * 100 / max_wheel;
    }
  }

  for (index = 0U; index < 4U; index++)
  {
    speed = wheel[index] * motors[index].trim_percent / 100;
    if (speed > 100)
    {
      speed = 100;
    }
    else if (speed < -100)
    {
      speed = -100;
    }

    target_pwm[index] = (int16_t)(speed * PWM_MAX_VALUE / 100);
    if ((target_pwm[index] != 0) &&
        (abs_i32(target_pwm[index]) < PWM_MIN_RUN))
    {
      target_pwm[index] = (target_pwm[index] > 0)
                          ? PWM_MIN_RUN : -PWM_MIN_RUN;
    }
  }
}

static void start_motion(int16_t vx, int16_t vy, int16_t wz)
{
  set_motion(vx, vy, wz);
  motion_active = 1U;
  motion_deadline = HAL_GetTick() + MOTION_TIMEOUT_MS;
}

static void process_command(uint8_t byte)
{
  uint8_t command;

  if (vector_collecting != 0U)
  {
    if ((byte == '\n') || (byte == '\r'))
    {
      vector_buffer[vector_length] = '\0';
      vector_collecting = 0U;
      process_vector();
    }
    else if (vector_length < (VECTOR_BUFFER_SIZE - 1U))
    {
      vector_buffer[vector_length++] = (char)byte;
    }
    else
    {
      vector_collecting = 0U;
      uart_puts("ERR vector too long\r\n");
    }
    return;
  }

  command = (uint8_t)((byte >= 'a' && byte <= 'z') ? byte - 32U : byte);

  switch (command)
  {
    case 'F': start_motion(100, 0, 0);    uart_puts("F\r\n"); break;
    case 'B': start_motion(-100, 0, 0);   uart_puts("B\r\n"); break;
    case 'L': start_motion(0, -100, 0);   uart_puts("L\r\n"); break;
    case 'R': start_motion(0, 100, 0);    uart_puts("R\r\n"); break;
    case 'Q': start_motion(0, 0, 100);    uart_puts("Q\r\n"); break;
    case 'E': start_motion(0, 0, -100);   uart_puts("E\r\n"); break;
    case 'G': start_motion(71, -71, 0);   uart_puts("FL\r\n"); break;
    case 'I': start_motion(71, 71, 0);    uart_puts("FR\r\n"); break;
    case 'H': start_motion(-71, -71, 0);  uart_puts("BL\r\n"); break;
    case 'J': start_motion(-71, 71, 0);   uart_puts("BR\r\n"); break;
    case 'K':
      if (motion_active != 0U)
      {
        motion_deadline = HAL_GetTick() + MOTION_TIMEOUT_MS;
      }
      break;
    case 'S':
      motion_active = 0U;
      motion_vx = 0;
      motion_vy = 0;
      motion_wz = 0;
      motors_hard_stop();
      uart_puts("STOP\r\n");
      break;
    case '+':
      if (speed_percent < MAX_SPEED_PERCENT)
      {
        speed_percent = (uint8_t)(speed_percent + SPEED_STEP_PERCENT);
        if (speed_percent > MAX_SPEED_PERCENT)
        {
          speed_percent = MAX_SPEED_PERCENT;
        }
      }
      if (motion_active != 0U)
      {
        set_motion(motion_vx, motion_vy, motion_wz);
        motion_deadline = HAL_GetTick() + MOTION_TIMEOUT_MS;
      }
      uart_puts((speed_percent == 100U) ? "SPD=100\r\n" : "SPD+\r\n");
      break;
    case '-':
      if (speed_percent > MIN_SPEED_PERCENT)
      {
        speed_percent = (uint8_t)(speed_percent - SPEED_STEP_PERCENT);
        if (speed_percent < MIN_SPEED_PERCENT)
        {
          speed_percent = MIN_SPEED_PERCENT;
        }
      }
      if (motion_active != 0U)
      {
        set_motion(motion_vx, motion_vy, motion_wz);
        motion_deadline = HAL_GetTick() + MOTION_TIMEOUT_MS;
      }
      uart_puts((speed_percent == 20U) ? "SPD=20\r\n" : "SPD-\r\n");
      break;
    case 'V':
      vector_length = 0U;
      vector_collecting = 1U;
      break;
    default:
      break;
  }
}

static uint8_t parse_int16(const char **cursor, int16_t *value)
{
  int32_t result = 0;
  int8_t sign = 1;
  uint8_t has_digit = 0U;

  while ((**cursor == ' ') || (**cursor == ','))
  {
    (*cursor)++;
  }
  if (**cursor == '-')
  {
    sign = -1;
    (*cursor)++;
  }
  while ((**cursor >= '0') && (**cursor <= '9'))
  {
    has_digit = 1U;
    result = (result * 10) + (**cursor - '0');
    if (result > 1000)
    {
      return 0U;
    }
    (*cursor)++;
  }
  if (has_digit == 0U)
  {
    return 0U;
  }

  result *= sign;
  if (result > 100)
  {
    result = 100;
  }
  else if (result < -100)
  {
    result = -100;
  }
  *value = (int16_t)result;
  return 1U;
}

static void process_vector(void)
{
  const char *cursor = vector_buffer;
  int16_t vx;
  int16_t vy;
  int16_t wz;

  if ((parse_int16(&cursor, &vx) == 0U) ||
      (parse_int16(&cursor, &vy) == 0U) ||
      (parse_int16(&cursor, &wz) == 0U))
  {
    uart_puts("ERR V,fwd,right,ccw\r\n");
    return;
  }

  start_motion(vx, vy, wz);
  uart_puts("V OK\r\n");
}
/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
