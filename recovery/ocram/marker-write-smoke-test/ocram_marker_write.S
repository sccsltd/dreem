.syntax unified
.arch armv7-a
.cpu cortex-a7
.global _start
_start:
  ldr r0, =0x0091f000
  ldr r1, =0x4452454d
  str r1, [r0]
1:
  b 1b
