import random
#import struct
#import time

import cc1101 #type: ignore
from cc1101.options import _TransceiveMode


with cc1101.CC1101() as radio:

    #baudrate = int(input("Enter baudrate (bps): "))
    #modFormat = input("FSK2, FSK4, GFSK, ASK_OOK, or MSK? ")

    ## Transmission Variables ##
    radio.set_base_frequency_hertz(433000000)
    #radio.set_symbol_rate_baud(baudrate)
    #radio.set_sync_word(b'\x91\xd3') # If you're a different school, make this (Or the frequency) different
    #radio.set_preamble_length_bytes(4)
    #radio.disable_checksum()
    #radio.set_packet_length_bytes(2)

    radio._set_modulation_format(cc1101.ModulationFormat.GFSK)
    #radio._set_transceive_mode(_TransceiveMode.ASYNCHRONOUS_SERIAL)
    #radio.set_output_power([0xC0]) #, 0xC2]) # See datasheet: Table 39 and Section 24

    print("Radio config:", radio)

    while True:
        string = random.randbytes(2)
        input(f"Press any key to send {string}")

        # Send Data
        radio.transmit(string)

        print("String Sent")
