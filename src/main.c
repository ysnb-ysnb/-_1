#include <stdint.h>

#define RCC_BASE      0x40021000UL
#define GPIOA_BASE    0x40010800UL
#define GPIOB_BASE    0x40010C00UL
#define USART1_BASE   0x40013800UL
#define TIM4_BASE     0x40000800UL
#define SYSTICK_BASE  0xE000E010UL

#define RCC_APB2ENR  (*(volatile uint32_t *)(RCC_BASE + 0x18UL))
#define RCC_APB1ENR  (*(volatile uint32_t *)(RCC_BASE + 0x1CUL))

#define GPIOA_CRH    (*(volatile uint32_t *)(GPIOA_BASE + 0x04UL))
#define GPIOB_CRL    (*(volatile uint32_t *)(GPIOB_BASE + 0x00UL))
#define GPIOB_CRH    (*(volatile uint32_t *)(GPIOB_BASE + 0x04UL))
#define GPIOB_BSRR   (*(volatile uint32_t *)(GPIOB_BASE + 0x10UL))

#define USART1_SR    (*(volatile uint32_t *)(USART1_BASE + 0x00UL))
#define USART1_DR    (*(volatile uint32_t *)(USART1_BASE + 0x04UL))
#define USART1_BRR   (*(volatile uint32_t *)(USART1_BASE + 0x08UL))
#define USART1_CR1   (*(volatile uint32_t *)(USART1_BASE + 0x0CUL))

#define TIM4_CR1     (*(volatile uint32_t *)(TIM4_BASE + 0x00UL))
#define TIM4_EGR     (*(volatile uint32_t *)(TIM4_BASE + 0x14UL))
#define TIM4_CCMR1   (*(volatile uint32_t *)(TIM4_BASE + 0x18UL))
#define TIM4_CCER    (*(volatile uint32_t *)(TIM4_BASE + 0x20UL))
#define TIM4_PSC     (*(volatile uint32_t *)(TIM4_BASE + 0x28UL))
#define TIM4_ARR     (*(volatile uint32_t *)(TIM4_BASE + 0x2CUL))
#define TIM4_CCR1    (*(volatile uint32_t *)(TIM4_BASE + 0x34UL))

#define SYST_CSR     (*(volatile uint32_t *)(SYSTICK_BASE + 0x00UL))
#define SYST_RVR     (*(volatile uint32_t *)(SYSTICK_BASE + 0x04UL))
#define SYST_CVR     (*(volatile uint32_t *)(SYSTICK_BASE + 0x08UL))

#define RCC_APB2ENR_AFIOEN   (1UL << 0)
#define RCC_APB2ENR_IOPAEN   (1UL << 2)
#define RCC_APB2ENR_IOPBEN   (1UL << 3)
#define RCC_APB2ENR_USART1EN (1UL << 14)
#define RCC_APB1ENR_TIM4EN   (1UL << 2)

#define USART_SR_RXNE (1UL << 5)
#define USART_SR_TXE  (1UL << 7)
#define USART_CR1_RE  (1UL << 2)
#define USART_CR1_TE  (1UL << 3)
#define USART_CR1_UE  (1UL << 13)

#define SYST_CSR_ENABLE     (1UL << 0)
#define SYST_CSR_COUNTFLAG  (1UL << 16)

#define MOTOR_IN1_PIN 12U
#define MOTOR_IN2_PIN 13U
#define PWM_MAX       399UL
#define TEST_DUTY     100UL
#define RUN_TIME_MS   1500UL

typedef enum {
    MOTOR_STOP = 0,
    MOTOR_FORWARD,
    MOTOR_REVERSE
} motor_state_t;

static volatile uint32_t g_ms;
static motor_state_t g_motor_state = MOTOR_STOP;
static uint32_t g_stop_at_ms;

static void systick_init(void)
{
    /*
     * SysTick uses HCLK/8 = 1 MHz at reset. A reload value of 999
     * produces a 1 ms polling tick.
     */
    SYST_RVR = 999UL;
    SYST_CVR = 0UL;
    SYST_CSR = SYST_CSR_ENABLE;
}

static void systick_poll(void)
{
    if ((SYST_CSR & SYST_CSR_COUNTFLAG) != 0UL) {
        g_ms++;
    }
}

static uint32_t millis(void)
{
    systick_poll();
    return g_ms;
}

static void delay_ms(uint32_t delay)
{
    uint32_t started = millis();
    while ((millis() - started) < delay) {
    }
}

static void gpio_write(uint32_t pin, int high)
{
    if (high != 0) {
        GPIOB_BSRR = 1UL << pin;
    } else {
        GPIOB_BSRR = 1UL << (pin + 16UL);
    }
}

static void uart1_init(void)
{
    uint32_t crh;

    RCC_APB2ENR |= RCC_APB2ENR_AFIOEN |
                   RCC_APB2ENR_IOPAEN |
                   RCC_APB2ENR_IOPBEN |
                   RCC_APB2ENR_USART1EN;

    /*
     * PA9  USART1_TX: alternate-function push-pull, 50 MHz.
     * PA10 USART1_RX: floating input.
     */
    crh = GPIOA_CRH;
    crh &= ~((0xFUL << 4U) | (0xFUL << 8U));
    crh |= (0xBUL << 4U) | (0x4UL << 8U);
    GPIOA_CRH = crh;

    /* HSI is 8 MHz at reset. BRR=833 gives 9600 baud. */
    USART1_BRR = 833UL;
    USART1_CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
}

static void uart1_write_byte(uint8_t byte)
{
    while ((USART1_SR & USART_SR_TXE) == 0U) {
    }
    USART1_DR = byte;
}

static void uart1_write_string(const char *text)
{
    while (*text != '\0') {
        uart1_write_byte((uint8_t)*text);
        text++;
    }
}

static void motor_gpio_init(void)
{
    uint32_t crl;
    uint32_t crh;

    /* GPIO configuration is ignored unless the GPIOB clock is enabled first. */
    RCC_APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPBEN;

    /* PB6: TIM4_CH1 alternate-function push-pull, 50 MHz. */
    crl = GPIOB_CRL;
    crl &= ~(0xFUL << 24U);
    crl |= (0xBUL << 24U);
    GPIOB_CRL = crl;

    /* PB12 and PB13: push-pull outputs, 2 MHz. */
    crh = GPIOB_CRH;
    crh &= ~((0xFUL << 16U) | (0xFUL << 20U));
    crh |= (0x2UL << 16U) | (0x2UL << 20U);
    GPIOB_CRH = crh;
}

static void pwm_init(void)
{
    RCC_APB1ENR |= RCC_APB1ENR_TIM4EN;

    /*
     * 8 MHz / (399 + 1) = 20 kHz PWM.
     * PWM mode 1 on channel 1, active high.
     */
    TIM4_PSC = 0UL;
    TIM4_ARR = PWM_MAX;
    TIM4_CCR1 = 0UL;
    TIM4_CCMR1 = (6UL << 4U) | (1UL << 3U);
    TIM4_CCER = 1UL;
    TIM4_EGR = 1UL;
    TIM4_CR1 = (1UL << 7U) | (1UL << 0U);
}

static void motor_set_state(motor_state_t state)
{
    if (state == g_motor_state) {
        return;
    }

    TIM4_CCR1 = 0UL;
    gpio_write(MOTOR_IN1_PIN, 0);
    gpio_write(MOTOR_IN2_PIN, 0);
    delay_ms(5UL);

    if (state == MOTOR_FORWARD) {
        gpio_write(MOTOR_IN1_PIN, 1);
        gpio_write(MOTOR_IN2_PIN, 0);
    } else if (state == MOTOR_REVERSE) {
        gpio_write(MOTOR_IN1_PIN, 0);
        gpio_write(MOTOR_IN2_PIN, 1);
    }

    g_motor_state = state;
}

static void motor_run(motor_state_t state)
{
    motor_set_state(state);
    if (state == MOTOR_STOP) {
        g_stop_at_ms = 0UL;
        uart1_write_string("LEFT_FRONT STOP\r\n");
        return;
    }

    TIM4_CCR1 = TEST_DUTY;
    g_stop_at_ms = millis() + RUN_TIME_MS;
    if (state == MOTOR_FORWARD) {
        uart1_write_string("LEFT_FRONT FORWARD 25% 1.5s\r\n");
    } else {
        uart1_write_string("LEFT_FRONT REVERSE 25% 1.5s\r\n");
    }
}

static void motor_watchdog(void)
{
    if ((g_stop_at_ms != 0UL) &&
        ((int32_t)(millis() - g_stop_at_ms) >= 0)) {
        motor_set_state(MOTOR_STOP);
        g_stop_at_ms = 0UL;
        uart1_write_string("LEFT_FRONT STOP\r\n");
    }
}

int main(void)
{
    systick_init();
    motor_gpio_init();
    uart1_init();
    pwm_init();
    motor_set_state(MOTOR_STOP);

    uart1_write_string(
        "LEFT FRONT MOTOR TEST\r\n"
        "F=forward 25% 1.5s\r\n"
        "B=reverse 25% 1.5s\r\n"
        "S=stop\r\n");

    for (;;) {
        systick_poll();
        motor_watchdog();

        if ((USART1_SR & USART_SR_RXNE) != 0U) {
            char command = (char)(USART1_DR & 0xFFUL);

            if ((command == 'F') || (command == 'f')) {
                motor_run(MOTOR_FORWARD);
            } else if ((command == 'B') || (command == 'b')) {
                motor_run(MOTOR_REVERSE);
            } else if ((command == 'S') || (command == 's')) {
                motor_run(MOTOR_STOP);
            }
        }
    }
}
