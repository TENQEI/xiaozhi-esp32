#ifndef FLOWER_S3_CONFIG_H_
#define FLOWER_S3_CONFIG_H_

#include <driver/gpio.h>

#define AUDIO_INPUT_SAMPLE_RATE 16000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

// INMP441: left channel (L/R must be tied to GND).
#define AUDIO_I2S_MIC_GPIO_WS GPIO_NUM_4   // XIAO D3
#define AUDIO_I2S_MIC_GPIO_SCK GPIO_NUM_5  // XIAO D4
#define AUDIO_I2S_MIC_GPIO_DIN GPIO_NUM_6  // XIAO D5

// MAX98357A: separate I2S controller/clocks from the microphone.
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_7  // XIAO D8
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_8  // XIAO D9
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_9  // XIAO D10

#define BOOT_BUTTON_GPIO GPIO_NUM_0  // Onboard BOOT button
#define MAIN_BUTTON_GPIO GPIO_NUM_1  // XIAO D0; external normally-open contact to GND
#define RESTART_BUTTON_GPIO GPIO_NUM_2  // XIAO D1; external normally-open contact to GND
#define BUILTIN_LED_GPIO GPIO_NUM_21
#define BUILTIN_LED_OUTPUT_INVERT 1

#endif  // FLOWER_S3_CONFIG_H_
