from datetime import timedelta
import time

import cc1101
from cc1101.options import _TransceiveMode

with cc1101.CC1101() as radio:

    #baudrate = int(input("Enter baud rate (bps): "))
    #modFormat = input("FSK2, FSK4, GFSK, ASK_OOK, or MSK? ")

    ## Transmission Variables ##
    #radio.set_sync_mode(0b10, False) # No carrier sense threshold
    #radio._set_filter_bandwidth(60)

    radio.set_base_frequency_hertz(433000000)
    #radio.set_symbol_rate_baud(baudrate)
    #radio.set_sync_word(b'\x91\xd3')
    #radio.set_preamble_length_bytes(4)
    #radio.disable_checksum()
    #radio.set_packet_length_bytes(2)

    radio._set_modulation_format(cc1101.ModulationFormat.GFSK)
    #radio._set_transceive_mode(_TransceiveMode.ASYNCHRONOUS_SERIAL)
    radio._enable_receive_mode() # THIS MUST HAPPEN LAST

    print("Radio config:", radio)

    waitNum = 0
    gotNum = 0
    failedNum = 0

    while True:
        # Receive a packet
        # GPIO 24 goes High when a packet is available
        inDump = radio._wait_for_packet(timedelta(seconds=5), gdo0_gpio_line_name=b"GPIO24")
        #inDump = radio._get_received_packet()

        if inDump is None:
            print(f"Waited for packet {waitNum} time(s). {gotNum} packet(s) so far, {failedNum} CRC Fails.")
            waitNum += 1
            time.sleep(1)
            continue

        if inDump.checksum_valid == False:
            print("CRC Failed!!!")
            failedNum += 1
            # continue

        packet = inDump.payload
        gotNum += 1
        print(f"Received: {packet}")

        waitNum = 0
