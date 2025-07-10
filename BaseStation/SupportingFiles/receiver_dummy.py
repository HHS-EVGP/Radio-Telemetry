import cc1101
from datetime import timedelta
import time

with cc1101.CC1101(spi_bus=0, spi_chip_select=0) as radio:
    ## Transmission Variables ##
    #radio.set_sync_mode(0b10, False) # No carrier sense threshold
    #radio._set_filter_bandwidth(60)

    baudrate = int(input("Enter baud rate (bps): "))

    radio.set_base_frequency_hertz(433000000)
    radio.set_symbol_rate_baud(baudrate)
    radio.set_sync_word(b'\x91\xd3')
    radio.set_preamble_length_bytes(4)
    radio.disable_checksum()
    radio.set_packet_length_bytes(2)

    radio._set_modulation_format(cc1101.ModulationFormat.GFSK)
    radio._enable_receive_mode() # THIS MUST HAPPEN LAST
    print("Radio config:", radio)
    waitNum = 0

    while True:
        # Receive a packet
        # GPIO 24 goes High when a packet is available
        #inDump = radio._wait_for_packet(timedelta(seconds=5), gdo0_gpio_line_name=b"GPIO24")
        inDump = radio._get_received_packet()

        if inDump is None:
            print(f"Waited for packet {waitNum} time(s)")
            waitNum += 1
            time.sleep(1)
            continue

        if inDump.checksum_valid == False:
            print("CRC Failed!!!")
            # continue

        packet = inDump.payload
        print("Raw Packet:", packet)
