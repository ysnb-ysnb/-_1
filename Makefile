PROJECT       := left_front_motor_test
BUILD_DIR     := build
TARGET        := $(BUILD_DIR)/$(PROJECT)

PREFIX        := arm-none-eabi-
CC            := $(PREFIX)gcc
OBJCOPY       := $(PREFIX)objcopy
SIZE          := $(PREFIX)size

CPU           := -mcpu=cortex-m3 -mthumb
CFLAGS        := $(CPU) -std=c11 -O2 -g3 \
                 -Wall -Wextra -Werror \
                 -ffreestanding -fno-builtin -ffunction-sections -fdata-sections
ASFLAGS       := $(CPU) -g3 -x assembler-with-cpp
LDFLAGS       := $(CPU) -nostdlib -Wl,--gc-sections \
                 -Wl,-Map=$(TARGET).map -T linker.ld

C_SOURCES     := src/main.c
ASM_SOURCES   := src/startup_stm32f103c8.s
OBJECTS       := $(BUILD_DIR)/main.o $(BUILD_DIR)/startup_stm32f103c8.o

.PHONY: all clean

all: $(TARGET).elf $(TARGET).hex $(TARGET).bin
	$(SIZE) $(TARGET).elf

$(BUILD_DIR):
	@mkdir -p "$(BUILD_DIR)"

$(BUILD_DIR)/main.o: src/main.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -Isrc -c $< -o $@

$(BUILD_DIR)/startup_stm32f103c8.o: src/startup_stm32f103c8.s | $(BUILD_DIR)
	$(CC) $(ASFLAGS) -c $< -o $@

$(TARGET).elf: $(OBJECTS) linker.ld | $(BUILD_DIR)
	$(CC) $(OBJECTS) $(LDFLAGS) -o $@

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

clean:
	@rm -rf "$(BUILD_DIR)"

.DELETE_ON_ERROR:
