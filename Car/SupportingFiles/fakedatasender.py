import struct
import random

import cc1101 #type: ignore
import time


with cc1101.CC1101() as radio:

    ## Transmission Variables ##
    radio.set_base_frequency_hertz(433000000)
    radio.set_symbol_rate_baud(5000)
    radio.set_sync_word(b'\x91\xd3') # If you're a different school, make this (Or the frequency) different
    radio.set_preamble_length_bytes(4)
    radio.set_output_power([0xC0]) #, 0xC2]) # See datasheet: Table 39 and Section 24

    radio.set_packet_length_bytes(2)

    radio.disable_checksum()
    radio._set_modulation_format(cc1101.ModulationFormat.MSK)
    print(radio)

    while True:
        string = random.randbytes(2)
        input(f"Press any key to send {string}")

        # Send Data
        radio.transmit(string)

        print("String Sent")
