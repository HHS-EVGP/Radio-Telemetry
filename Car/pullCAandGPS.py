from smbus2 import SMBus, i2c_msg
import time
import random

ESP32_ADDR = 0x08

def request_string(command, read_len=16):
    with SMBus(1) as bus:
        # 0x01 is CA
        # 0x02 is GPS
        bus.write_byte(ESP32_ADDR, command)
        time.sleep(.05)  # wait for ESP to prepare response

        read = i2c_msg.read(ESP32_ADDR, read_len)
        bus.i2c_rdwr(read) # WHY DOES THERE NEED TO BE TWO????
        bus.i2c_rdwr(read) # IT BREAKS WHEN THERE IS ONLY ONE ):
        raw_bytes = bytes(read)
        # Decode only valid bytes, drop nulls and garbage
        return raw_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore').strip()

#for _ in range(25):
while True:
    if(random.choice([True,False])):
        print("Requesting CA:")
        print(request_string(0x01, read_len=32))
    else:
        print("Requesting GPS:")
        print(request_string(0x02, read_len=96))
    time.sleep(0.8)