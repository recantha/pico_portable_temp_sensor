from machine import Pin
from time import sleep
from pimoroni_i2c import PimoroniI2C
from breakout_bme280 import BreakoutBME280
from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY, PEN_RGB565
from pimoroni import RGBLED, Button
import network
from umqtt.simple import MQTTClient
from secrets import secrets

def hsv_to_rgb(h, s, v):
    if s == 0.0:
        return v, v, v
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6
    if i == 0:
        return v, t, p
    if i == 1:
        return q, v, p
    if i == 2:
        return p, v, t
    if i == 3:
        return p, q, v
    if i == 4:
        return t, p, v
    if i == 5:
        return v, p, q

def reading_to_colour(reading, minimum, maximum):
    reading = min(reading, maximum)
    reading = max(reading, minimum)

    print("Reading: ", reading)

    f_index = float(reading - minimum) / float(maximum - minimum)
    f_index *= len(colors) - 1
    index = int(f_index)

    print("Index: ", index)

    if index == len(colors) - 1:
        return colors[index]

    blend_b = f_index - index
    blend_a = 1.0 - blend_b

    a = colors[index]
    b = colors[index + 1]

    return [int((a[i] * blend_a) + (b[i] * blend_b)) for i in range(3)]

led = Pin("LED", Pin.OUT)

display = PicoGraphics(display=DISPLAY_PICO_DISPLAY, pen_type=PEN_RGB565, rotate=0)
display.set_backlight(0.8)

bar_width = 5

temp_min = 10
temp_max = 30
temperatures = []

humid_min = 0
humid_max = 100
humiditys = []

press_min = 50000
press_max = 120000
pressures = []

colors = [(0, 0, 255), (0, 255, 0), (255, 255, 0), (255, 0, 0)]

WIDTH, HEIGHT = display.get_bounds()
BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
print("Screen width: ", WIDTH, " height: ", HEIGHT)

PINS_I2C = {"sda": 8, "scl": 9}
i2c = PimoroniI2C(**PINS_I2C)
bme = BreakoutBME280(i2c)

button_a = Button(12)
button_b = Button(13)
button_x = Button(14)
button_y = Button(15)

# Default mode is to show temperatures
mode = "temperature"

def display_simple(message):
    global display
    display.set_pen(BLACK)
    display.clear()
    
    display.set_pen(WHITE)
    display.text(message, 0, 0, 0, 2)
    display.update()

    sleep(0.2)

wifi_enabled = False

def enable_wifi():
    global wifi_enabled
    
    wifi_enabled = True

def connect_wifi():
    # Connect to WiFi
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(secrets["WIFI_SSID"], secrets["WIFI_PASSWORD"])
    while wlan.isconnected() == False:
        print('Waiting for connection...', wlan.status())
        message = 'Waiting for connection...{}'.format(wlan.status())
        display_simple(message)
        sleep(1)
    print("Connected to WiFi")
    display_simple('Connected to WiFi {}'.format(secrets["WIFI_SSID"]))
    sleep(2)

def connect_mqtt():
    global mqtt_client
    display_simple('Connecting MQTT client')
    mqtt_client.connect()

if wifi_enabled == False:
    display_simple('WiFi not enabled')
    sleep(2)

display_simple('Creating MQTT client')
mqtt_client = MQTTClient(
    client_id=secrets["MQTT_CLIENT_ID"],
    server=secrets["ADAFRUIT_HOST"],
    user=secrets["ADAFRUIT_IO_USERNAME"],
    password=secrets["ADAFRUIT_IO_KEY"]
)

while True:
    # fills the screen with black
    display.set_pen(BLACK)
    display.clear()

    if button_a.is_pressed:
        mode = "temperature"
    elif button_b.is_pressed:
        mode = "humidity"
    elif button_x.is_pressed:
        mode = "pressure"
    elif button_y.is_pressed:
        enable_wifi()
        connect_wifi()
        connect_mqtt()

    # Get the various readings and append them to the relevant arrays
    (temperature, pressure, humidity) = bme.read()
    temperatures.append(temperature)
    humiditys.append(humidity)
    pressures.append(pressure)

    # shifts the relevant histories to the left by one sample
    if len(temperatures) > WIDTH // bar_width:
        temperatures.pop(0)

    if len(humiditys) > WIDTH // bar_width:
        humiditys.pop(0)

    if len(pressures) > WIDTH // bar_width:
        pressures.pop(0)

    i = 0

    # Set up common variables with specific values depending on the mode you're in
    if mode == "temperature":
        reading = temperature
        readings = temperatures
        (minimum, maximum) = (temp_min, temp_max)
        label = "Temp:"
    elif mode == "humidity":
        reading = humidity
        readings = humiditys
        (minimum, maximum) = (humid_min, humid_max)
        label = "Hmdy:"
    elif mode == "pressure":
        reading = pressure
        readings = pressures
        (minimum, maximum) = (press_min, press_max)
        label = "Pres:"

    for r in readings:
        # chooses a pen colour based on the temperature
        READING_COLOUR = display.create_pen(*reading_to_colour(r, minimum, maximum))

        print("Reading colour: ", READING_COLOUR)

        display.set_pen(READING_COLOUR)

        # draws the reading as a tall, thin rectangle
        display.rectangle(i, HEIGHT - (round(r) * 4), bar_width, HEIGHT)

        # the next tall thin rectangle needs to be drawn
        # "bar_width" (default: 5) pixels to the right of the last one
        i += bar_width

    # draws a white background for the text
    display.set_pen(WHITE)
    display.rectangle(0, HEIGHT-25, WIDTH, 25)

    # writes the reading as text in the white rectangle
    display.set_pen(BLACK)
    # display the label of the reading (i.e. what the reading is OF)
    display.text(label, 0, HEIGHT-25, 0, 3)
    # display the actual reading next to the label
    display.text("{:.2f}".format(reading), 80, HEIGHT-25, 0, 3)

    # time to update the display
    display.update()

    # Might as well blink the on-board LED as well
    led.toggle()

    if wifi_enabled:
        try:
            print("Trying to publish temperature ({})".format(temperature))
            mqtt_client.publish(secrets["ADAFRUIT_TOPIC_TEMPERATURE"], str(temperature))

            print("Trying to publish humidity ({})".format(humidity))
            mqtt_client.publish(secrets["ADAFRUIT_TOPIC_HUMIDITY"], str(humidity))

        except Exception as e:
            print(f'Failed to publish message: {e}')
            #display_simple(f'Failed to publish: {e}')

    # waits for 5 seconds
    sleep(5)

