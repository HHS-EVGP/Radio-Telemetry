def collector():
    try:
        import busio # type: ignore
        import serial # type: ignore
        import RPi.GPIO as GPIO  # type: ignore
        from adafruit_ads1x15.analog_in import AnalogIn # type: ignore
        import board # type: ignore
        #from adafruit_lsm6ds.lsm6dsox import LSM6DSOX # type: ignore
        import adafruit_ads1x15.ads1115 as ADS # type: ignore
        import cc1101
        import smbus # type: ignore

        import math
        import subprocess
        import time
        from datetime import datetime
        import struct
        import sqlite3

        # Set up stop button
        import sys
        from gpiozero import Button #type: ignore

        def stop_collector():
            print("Stop button pressed. Exiting collector.")
            sys.exit(0)

        stop_btn = Button(19)  # Example GPIO pin, adjust as needed
        stop_btn.when_pressed = stop_collector

        bus = smbus.SMBus(1)
        On_GPS_time = False

        # Connect to the car's database
        con = sqlite3.connect('./CarTelemetry.sqlite')
        cur = con.cursor()

        # Create the initial table (Named main)
        cur.execute('''
        CREATE TABLE IF NOT EXISTS main (
            time REAL UNIQUE PRIMARY KEY,
            amp_hours REAL,
            voltage REAL,
            current REAL,
            speed REAL,
            miles REAL,
            throttle REAL,
            brake REAL,
            motor_temp REAL,
            batt_1 REAL,
            batt_2 REAL,
            batt_3 REAL,
            batt_4 REAL,
            GPS_x REAL,
            GPS_y REAL,
            laps NUMERIC
        )
        ''')
        con.commit()

        # Find a list of days that are present in the database
        cur.execute('''
            SELECT DISTINCT
                DATE(time, 'unixepoch') AS day
                FROM main
                ORDER BY day;
        ''')
        days = cur.fetchall()

        # Create individual views for each existing day if they do not exist
        for day in days:
            cur.execute(f"""
            CREATE VIEW IF NOT EXISTS '{day[0]}'
            AS SELECT * FROM main
            WHERE DATE(time, 'unixepoch') = '{day[0]}';
            """)
        con.commit()

        # Setup Thermistor Values
        R1 = 13000.0
        c1 = 1.009249522e-03
        c2 = 2.378405444e-04
        c3 = 2.019202697e-07

        # Setup Send LED
        sendLED = 27
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(sendLED, GPIO.OUT)
        GPIO.output(sendLED, 0)

        # Setup i2C & Devices
        i2c = busio.I2C(board.SCL, board.SDA)
        analogA = ADS.ADS1115(i2c, address = 0x4B)
        analogB = ADS.ADS1115(i2c, address = 0x4A)

        # Setup Analog In Ports
        A0 = AnalogIn(analogA, ADS.P0) # battTemp1
        A1 = AnalogIn(analogA, ADS.P1) # battTemp2
        A2 = AnalogIn(analogA, ADS.P2) # battTemp3
        A3 = AnalogIn(analogA, ADS.P3) # battTemp4
        B0 = AnalogIn(analogB, ADS.P0) # motorTemp
        B1 = AnalogIn(analogB, ADS.P1) # throttle
        #B2 = AnalogIn(analogB, ADS.P2) # Port not used
        B3 = AnalogIn(analogB, ADS.P3) # brake

        # Setup Serial for Cycle Anyalist
        cycleAnalyst = serial.Serial('/dev/serial0',baudrate=9600,timeout=5)


        # Serial handler for Cycle Analyst
        def UART_CA():
            # Input from CA is: amp_hours|voltage|current|speed|miles
            try:
                if cycleAnalyst.in_waiting > 0:
                    line = cycleAnalyst.readline().decode('utf-8').strip()
                    if line:
                        amp_hours, voltage, current, speed, miles = line.split('\t')
                        amp_hours = float(amp_hours)
                        voltage = float(voltage)
                        current = float(current)
                        speed = float(speed)
                        miles = float(miles)
                        return [amp_hours, voltage, current, speed, miles]

                else:
                    return [float('nan')] * 5

            except Exception as e:
                print(f"Error in SERIAL_CA function: {e}")
                return [float('nan')] * 5


        def set_system_time(gpstime, date):
            """Set the system time using the date command."""

            # Extract hours, minutes, and seconds from timestamp
            hours = gpstime[:2]
            minutes = gpstime[2:4]
            seconds = gpstime[4:]

            # Adjust for our timezone
            hours = int(hours)  - 4

            # Extract day, month, and year from date
            day = date[:2]
            month = date[2:4]
            year = 2000 + int(date[4:]) # Change this in 75 years; This is a limitation of the $GPRMC format

            # Format the date and time for the `date` command
            formatted_time = f"{year}-{month}-{day} {hours}:{minutes}:{seconds}"

            # Set the system time using the `date` command
            subprocess.run(["sudo", "date", "-s", formatted_time], check=True)
            print("System time sucessfully set to GPS time:", datetime.now())

            global On_GPS_time
            On_GPS_time = True


        def read_full_sentence():
            sentence = ""
            for _ in range(10):
                try:
                    data = bus.read_i2c_block_data(0x42, 0, 32)
                    valid_data = ''.join([chr(i) for i in data if 32 <= i <= 126 or i in (10, 13)])
                    sentence += valid_data
                    if '\n' in valid_data:
                        break
                except OSError as e:
                    if e.errno == 5:
                        print("ESP not online")
                    else:
                        print("Error:", e)
                    break
                time.sleep(0.01)
            return sentence


        # UART handler for GPS
        def UART_GPS():
            try:
                data = read_full_sentence()

                if data:

                    killall, gpstime, pos_status, lat, lat_dir, lon, lon_dir, speed, track_true, date, \
                        mag_var, var_dir, checksum = data.split(',')

                    # If no GPS fix, return nan for all variables
                    if pos_status == 'V':
                        print("No GPS fix!!!")
                        return [float('nan')] * 2

                    # Set System time to gps time if not done yet
                    if not On_GPS_time:
                        set_system_time(gpstime, date)

                    # Convert latitude and longitude to decimal degrees
                    lat = float(lat[:2]) + float(lat[2:]) / 60.0
                    if lat_dir == 'S':
                        lat = -lat

                    lon = float(lon[:3]) + float(lon[3:]) / 60.0
                    if lon_dir == 'W':
                        lon = -lon

                    # Convert decimal degrees to radians
                    lat = math.radians(lat)
                    lon = math.radians(lon)

                    # The IAU nominal "zero tide" equatorial radius of the Earth
                    R = 6378100

                    # Convert to Cartesian coordinates
                    GPS_x = R * math.cos(lat) * math.cos(lon)
                    GPS_y = R * math.cos(lat) * math.sin(lon)

                    # Success!
                    return GPS_x, GPS_y

            except Exception as e:
                print(f"Error in UART_GPS function: {e}")

            # didn't work out
            return [float('nan')] * 2


        def thermistor(idx):
            idx = idx*1024/32768
            R2 = R1 * (1023.0 / float(idx) - 1.0)
            logR2 = math.log(R2)
            T = 1.0 / (c1 + c2 * logR2 + c3 * logR2**3)
            T = T - 273.15  # Convert from Kelvin to Celsius
            #T = (T * 9.0) / 5.0 + 32.0  # Convert from Celsius to Fahrenheit
            return T


        def mapTo(x, minI, maxI, minO, maxO):
            return (x-minI)/(maxI-minI)*(maxO-minO)+minO


        def analogPull():
            # Throttle Value
            try:
                throttle = mapTo(B1.value, 6500, 33000, 0, 1000)
            except:
                throttle = float('nan')

            # Brake Value
            try:
                brake = mapTo(B3.value, 14500, 21500, 0, 1000)
            except:
                brake = float('nan')

            # Motor Temperature
            try:
                motor_temp = thermistor(B0.value)
            except:
                motor_temp = float('nan')

            # Battery 1 Temperature
            try:
                batt_1 = thermistor(A0.value)
            except:
                batt_1 = float('nan')

            # Battery 2 Temperature
            try:
                batt_2 = thermistor(A1.value)
            except:
                batt_2 = float('nan')

            # Battery 3 Temperature
            try:
                batt_3 = thermistor(A2.value)
            except:
                batt_3 = float('nan')

            # Battery 4 Temperature
            try:
                batt_4 = thermistor(A3.value)
            except:
                batt_4 = float('nan')

            return throttle, brake, motor_temp, batt_1, batt_2, batt_3, batt_4


        insert_data_sql = """
            INSERT INTO main (
                time, Throttle, Brake, Motor_temp, Batt_1, Batt_2, Batt_3, Batt_4,
                amp_hours, Voltage, Current, Speed, Miles, GPS_X, GPS_Y
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """


        with cc1101.CC1101(spi_bus=0, spi_chip_select=1) as radio:

            ## Transmission Variables ##
            radio.set_base_frequency_hertz(433000000) # Set to 915000000 once we get the right antenas
            radio.set_symbol_rate_baud(6000)
            radio.set_sync_word(b'\x91\xd3') # If you're a different school, make this (Or the frequency) different
            radio.set_preamble_length_bytes(4)
            radio.set_output_power([0xC0]) #, 0xC2]) # See datasheet: Table 39 and Section 24

            radio._set_modulation_format(cc1101.ModulationFormat.GFSK)
            print(radio)

            while True:
                # Get Data
                timestamp = time.time()
                ampHrs, voltage, current, speed, miles = UART_CA()
                throttle, brake, motorTemp, batt1, batt2, batt3, batt4 = analogPull()
                gpsX, gpsY = UART_GPS()

                # Designate wich variables will be encoded wich way
                data64 = [timestamp, gpsX, gpsY] # 24 bytes
                data16 = [throttle, brake, motorTemp, batt1, batt2, batt3, batt4, \
                          ampHrs, voltage, current, speed, miles] # 24 bytes
                ### 24 + 24 = 48 bytes, wich is under the 56 byte buffer limit of the cc1101*
                ### *Total limit is 64 bytes, but 8 are taken up by the pramble, sync word, and chekcsum

                print(data64)
                print(data16)

                # Combine all data together for logging
                data = [timestamp, throttle, brake, motorTemp, batt1, batt2, batt3, batt4, \
                        ampHrs, voltage, current, speed, miles, gpsX, gpsY]

                # Add data to the database:
                cur.execute(insert_data_sql, data)
                con.commit()
                print("Logged Data")

                # Attempt to send data
                try:
                    packet = b""

                    # Encode time and GPS as 64 bit
                    packet += struct.pack("<" + "d" * len(data64), *data64)

                    # Encode ADC and CA Values as 16 bit
                    packet += struct.pack("<" + "e" * len(data16), *data16)

                    # Encode 32 bit data
                    #packet += struct.pack("<" + "f" * len(data32), *data32)

                    # Send Data
                    GPIO.output(sendLED, 1)
                    radio.transmit(packet)
                    GPIO.output(sendLED, 0)
                    print("Packet sent")

                except Exception as e:
                    print("Error sending data:", e)

    except Exception:
        sys.exit(1)

if __name__ == "__main__":
    collector()
