import time
import subprocess
from gpiozero import LED, Button #type: ignore
from collector import collector
import sys

import logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - SM - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logging.info("Starting button script.")

# LED setup
green_led = LED(17)  # Script running
white_led = LED(22)  # PI has power
red_led = LED(4)     # Script failed

# Button setup
#stop_btn = Button(19)    # STOP script
start_btn = Button(13)   # START script
restart_btn = Button(26) # RESTART PI

running = 0 # Nothing running

def start_script():
    try:
        global running
        if running == 1:
            print("Collector already running")
            logging.info("Collector already running")
            return
            
        red_led.off()
        for i in range(4):
            green_led.off()
            time.sleep(0.1)
            green_led.on()
            time.sleep(0.1)
        logging.info("Started with Button")

        running = 1
        try:
            collector()
        except SystemExit as exit:
            running = 0
            green_led.off()
            if exit.code == 0:
                logging.info("Collector stopped with stop button")
                print("Collector stopped with stop button")
            else:
                red_led.on()
                logging.info("Collector exited with code:", exit.code)
                print("Collector exited with code:", exit.code)
            

    except Exception as e:
        red_led.on()
        green_led.off()
        logging.info("Failed to start with button", e)
        print("Failed to start script", e)

def restart_pi():
    logging.info("Restarting PI from buttons")
    print("Initiating system restart...")
    
    for i in range(10):
        green_led.on()
        red_led.on()
        white_led.on()
        time.sleep(0.15)
        green_led.off()
        red_led.off()
        white_led.off()
        time.sleep(0.15)
        
    subprocess.run(["sudo reboot"])

# Turn on power indicator
white_led.on()

# Set up button actions
start_btn.when_pressed = start_script
restart_btn.when_pressed = restart_pi

# Start collector initially
start_script()