/*
 * Copyright (c) 2023 Nordic Semiconductor ASA
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/drivers/gpio.h>

#define SERVICE_DATA_LEN        7
#define SERVICE_UUID            0xfcd2      /* BTHome service UUID */
#define IDX_RUNNING               4           /* Index of byte of running in service data*/
#define IDX_WATCHDOG              6           /* Index of byte of watchdog in service data*/

#define ADV_PARAM BT_LE_ADV_PARAM(BT_LE_ADV_OPT_USE_IDENTITY, \
				  BT_GAP_ADV_SLOW_INT_MIN, \
				  BT_GAP_ADV_SLOW_INT_MAX, NULL)


#define MAX_OFF_PERIODS           20 

static const struct gpio_dt_spec pm_done = GPIO_DT_SPEC_GET(DT_NODELABEL(pm_done), gpios);
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(DT_NODELABEL(button), gpios);


static uint8_t service_data[SERVICE_DATA_LEN] = {
	BT_UUID_16_ENCODE(SERVICE_UUID),
	0x40,
	0x27,	/* Running */
	0x00,	/* Off Byte */
	0x0F,   /* Generic Boolean (watchdog) */
	0x00    /* Watchdog Byte */
};

static struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR),
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
	BT_DATA(BT_DATA_SVC_DATA16, service_data, ARRAY_SIZE(service_data))
};

static void bt_ready(int err)
{
	if (err) {
		printk("Bluetooth init failed (err %d)\n", err);
		return;
	}

	printk("Bluetooth initialized\n");

	/* Start advertising */
	err = bt_le_adv_start(ADV_PARAM, ad, ARRAY_SIZE(ad), NULL, 0);
	if (err) {
		printk("Advertising failed to start (err %d)\n", err);
		return;
	}
}

int main(void)
{
	int err;
	int ret;
	int off_periods = 0;

	printk("Sensor Starting\n");

	/* Initialize Peripherals */

	if(!device_is_ready(button.port)){
		return 0;
	}

	/* Initialize the Bluetooth Subsystem */
	err = bt_enable(bt_ready);
	if (err) {
		printk("Bluetooth init failed (err %d)\n", err);
		return 0;
	}

	err = gpio_pin_configure_dt(&pm_done, GPIO_OUTPUT_LOW);
        if (err) {
		return 0;
	}

	err = gpio_pin_configure_dt(&button, GPIO_INPUT);
        if (err) {
		return 0;
	}

	/* Startup State:
	 * Check if flow sensor woke device */

	// Poll flow switch several times
	for (int i = 0; i < 3; i++) {
		ret = gpio_pin_get_dt(&button);
		if (ret == 1) {
			off_periods++;
		} else if (ret != 0) {
			return 0;
		}
		k_sleep(K_MSEC(50));
	}

	if (off_periods == 0) {
		// This is a watchdog wake
		service_data[IDX_WATCHDOG] = 0x01;
	}

	for (;;) {
		ret = gpio_pin_get_dt(&button);
		if (ret == 1) {
			service_data[IDX_RUNNING] = 0x01;
			service_data[IDX_WATCHDOG] = 0x00;
			off_periods = 0;
		} else if (ret == 0) {
			service_data[IDX_RUNNING] = 0x00;
			off_periods++;
		} else {
			return 0;
		}
		err = bt_le_adv_update_data(ad, ARRAY_SIZE(ad), NULL, 0);
		if (err) {
			printk("Failed to update advertising data (err %d)\n", err);
		}

		// Tap has been checked to be off long enough, tap is either turned off or this is a watchdog.
		if (off_periods == MAX_OFF_PERIODS) {
			// Switch off the power rail
			err = gpio_pin_set_dt(&pm_done, 1);
		}

		k_sleep(K_MSEC(BT_GAP_ADV_SLOW_INT_MIN));
	}
	return 0;
}
