.syntax unified
.cpu cortex-m3
.thumb

.section .isr_vector,"a",%progbits
.global g_pfnVectors
.type g_pfnVectors, %object
g_pfnVectors:
  .word _estack
  .word Reset_Handler
  .word Default_Handler
  .word Default_Handler
  .word Default_Handler
  .word Default_Handler
  .word Default_Handler
  .word 0
  .word 0
  .word 0
  .word 0
  .word Default_Handler
  .word Default_Handler
  .word 0
  .word Default_Handler
  .word Default_Handler

  .rept 43
  .word Default_Handler
  .endr

.size g_pfnVectors, .-g_pfnVectors

.text
.type Reset_Handler, %function
.global Reset_Handler
Reset_Handler:
  ldr r0, =_sdata
  ldr r1, =_edata
  ldr r2, =_sidata
  movs r3, #0

copy_data:
  cmp r0, r1
  bcs clear_bss_start
  ldr r4, [r2, r3]
  str r4, [r0, r3]
  adds r3, r3, #4
  b copy_data

clear_bss_start:
  ldr r0, =_sbss
  ldr r1, =_ebss
  movs r2, #0

clear_bss:
  cmp r0, r1
  bcs call_main
  str r2, [r0]
  adds r0, r0, #4
  b clear_bss

call_main:
  bl main

hang:
  b hang

.size Reset_Handler, .-Reset_Handler

.type Default_Handler, %function
.global Default_Handler
Default_Handler:
  b Default_Handler

.size Default_Handler, .-Default_Handler

.end
