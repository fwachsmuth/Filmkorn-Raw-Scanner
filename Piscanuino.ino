/*
 * Controller for the Noris based Film Scanner
 *
 * Todo:
 *
 * - Add I2C Communication with the Raspi
 *   - Receive something on the Raspi and show it.
 *   - Make it a loop
 *   - Implement commands on the Raspi:
 *     - Zoom in
 *     - Zoom out
 *     - Take a Raw
 *     - Say "I am ready for the next photo"
 * Raspi Todos:
 * - enter init 2 after boot
 * - /opt/vc/bin/tvservice -o # Display aus
 * - /opt/vc/bin/tvservice -p # Display an
 *
 *
 * - FInd out why I can't program inside the board
 * Is the USB Friend really borked?
 *
 * - Draw Schematics already
 *
 */

#include <Wire.h>
#include <WireData.h>

const byte SLAVE_ADDRESS = 42; // Our i2c address here

// Define the Control Buttons
enum ControlButton {
  NONE,  // No Button pressed
  ZOOM,  // Toggle
  LIGHT, // Toggle
  REV,   // Radio
  REV1,  // Push
  STOP,  // Radio
  FWD1,  // Push
  FWD,   // Radio
  SCAN   // Radio
} currentButton = NONE, prevButtonChoice = NONE;

/* Define the States we can be in
 * enum {
 *   IDLE,
 *   SCAN,
 *   PREVIEW,
 *   RUN
 * } state = IDLE, prevState = IDLE;
 */

// Define the motor states
enum {
  REV = -1,
  STOPPED,
  FWD
} motorState = STOPPED;

// Define the Hardware wiring
#define FAN_PIN         8
#define LAMP_PIN        9
#define MOTOR_A_PIN     6   // PWM
#define MOTOR_B_PIN     5   // PWM
#define TRIGGER_PIN     7
#define EYE_PIN         2   // ISR
#define BUTTONS_A_PIN   A0
#define BUTTONS_B_PIN   A1
#define SINGLE_STEP_POT A2
#define CONT_RUN_POT    A3

// Define the I2C commands we need
//                              Raspi      Arduino
#define CMD_IDLE        0   /*        <---          */
#define CMD_PING        1   /*        <---          */
#define CMD_ZOOMCYCLE   2   /*        <---          */
#define CMD_SHOOTRAW    3   /*        <---          */
#define CMD_READY       4   /*        --->          */
#define CMD_LAMP_ON     5   /*        <---          */
#define CMD_LAMP_OFF    6   /*        <---          */

// Define some constants
uint8_t  fps18MotorPower;
uint8_t  singleStepMotorPower;

// Define some global variables
bool    lampMode = false;
bool    zoomMode = false;
bool    isScanning = false;
uint8_t ISRcount = 0;
uint8_t speed = 0;
uint8_t nextPiCmd;

volatile bool haveI2Cdata = false;
volatile uint8_t i2cCommand;

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  pinMode(BUTTONS_A_PIN, INPUT);
  pinMode(BUTTONS_B_PIN, INPUT);
  pinMode(SINGLE_STEP_POT, INPUT);
  pinMode(CONT_RUN_POT, INPUT);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(LAMP_PIN, OUTPUT);
  pinMode(MOTOR_A_PIN, OUTPUT);
  pinMode(MOTOR_B_PIN, OUTPUT);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(EYE_PIN, INPUT);

  // Stop the engines
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, 0);

  Wire.begin(SLAVE_ADDRESS);
  Wire.onReceive(i2cReceive);
  Wire.onRequest(i2cRequest);
}

void loop() {

  if (isScanning && haveI2Cdata && i2cCommand == CMD_READY) {
    motorFWD1();                // advance
    delay(750);                 // would be better to wait for the camera to be finished.
    nextPiCmd = CMD_SHOOTRAW;   // tell to shoot
  }

  // Read the trim pots to determine PWM width for the Motor
  fps18MotorPower = map(analogRead(CONT_RUN_POT), 0, 1023, 255, 100); // 100 since lower values don't start the motor
  singleStepMotorPower = map(analogRead(SINGLE_STEP_POT), 0, 1023, 255, 100);

  currentButton = pollButtons();

  if (currentButton != prevButtonChoice) {
    prevButtonChoice = currentButton;

    if (!isScanning || currentButton == STOP) {
      switch (currentButton) {
        case NONE:
        default:
          break;
        case ZOOM:
          setZoomMode(!zoomMode);
          break;
        case LIGHT:
          setLampMode(!lampMode);
          break;
        case STOP:
          if (isScanning) {
            setLampMode(false);
            isScanning = false;
            Serial.println("Scanning mode: 0");
            // ...
          } else {
            stopMotor();
          }
          break;
        case REV:
          if (motorState == FWD)
            stopBriefly();
          motorState = REV;
          Serial.print("Motor: << at Speed ");
          Serial.println(fps18MotorPower);
          motorRev();
          break;
        case REV1:
          if (motorState != STOPPED) {
            Serial.println("Motor not stopped.");
            break;
          }
          Serial.print("< at Speed ");
          Serial.println(singleStepMotorPower);
          motorREV1();
          break;
        case FWD1:
          if (motorState != STOPPED)
            break;
          Serial.print("> at Speed ");
          Serial.println(singleStepMotorPower);
          motorFWD1();
          break;
        case FWD:
          if (motorState == REV)
            stopBriefly();
          motorState = FWD;
          Serial.print("Motor: >> at Speed ");
          Serial.println(fps18MotorPower);
          motorFwd();
          break;
        case SCAN:
          if (motorState != STOPPED)
            stopBriefly();
          setZoomMode(false);
          setLampMode(true);
          isScanning = true;
          Serial.println("Scanning mode: 1");
          // ... (don't forget to detach ISR)
          break;
      }
    }
  }
}

void stopMotor() {
  // ...
  motorState = STOPPED;
  Serial.println("Motor: Stop");

  // Enable the below three lines if breaking makes sense

  digitalWrite(MOTOR_A_PIN, HIGH);
  digitalWrite(MOTOR_B_PIN, HIGH);
//  delay(10); // geht nicht im ISR und hier sind wir ggf im ISR!
//  digitalWrite(MOTOR_A_PIN, LOW);
//  digitalWrite(MOTOR_B_PIN, LOW);
}

void stopBriefly() {
  // This makes direct direction changes less harsh
  stopMotor();
  Serial.println("(Briefly...)");
  delay(250);
}

void setLampMode(bool mode) {
  if (mode == lampMode)
    return;
  if (!mode && zoomMode)
    setZoomMode(false);
  lampMode = mode;
  Serial.print("Lamp mode: ");
  Serial.println(lampMode);

  if (lampMode) {
    digitalWrite(FAN_PIN, HIGH);
    digitalWrite(LAMP_PIN, HIGH);
  } else {
    digitalWrite(FAN_PIN, LOW);
    digitalWrite(LAMP_PIN, LOW);
  }
}

void setZoomMode(bool mode) {
  if (mode == zoomMode)
    return;
  if (mode && !lampMode)
    setLampMode(true);

  zoomMode = mode;
  Serial.print("Zoom mode: ");
  Serial.print(zoomMode);

  if (zoomMode) {
    Serial.println(". Telling Raspi to zoom in");
  } else {
    Serial.println(". Telling Raspi to zoom out");
  }
}

void motorFWD1() {
  EIFR = 1; // clear flag for interrupt
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, RISING);
  analogWrite(MOTOR_A_PIN, singleStepMotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorREV1() {
  EIFR = 1; // clear flag for interrupt
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, RISING);
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, singleStepMotorPower);
}

void motorFwd() {
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
  analogWrite(MOTOR_A_PIN, fps18MotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorRev() {
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, fps18MotorPower);
}

void stopMotorISR() {
  motorState = STOPPED;
  digitalWrite(MOTOR_A_PIN, HIGH);
  digitalWrite(MOTOR_B_PIN, HIGH);
//  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
}

ControlButton pollButtons() {
  int buttonBankA;
  int buttonBankB;
  static bool noButtonPressed;
  ControlButton buttonChoice;

  buttonBankA = analogRead(BUTTONS_A_PIN);
  buttonBankB = analogRead(BUTTONS_B_PIN);
  delay(10); // debounce (since button release bounce is not covered in the FSM)

  if (noButtonPressed) {
    if (buttonBankA < 2 && buttonBankB < 2) {
      buttonChoice = NONE;
    } else if (buttonBankA > 30 && buttonBankA < 70) {
      buttonChoice = ZOOM;
      nextPiCmd = CMD_ZOOMCYCLE;
    } else if (buttonBankA > 120 && buttonBankA < 160) {
      buttonChoice = LIGHT;
      if (lampMode) {
        nextPiCmd = CMD_LAMP_OFF;
      } else {
        nextPiCmd = CMD_LAMP_ON;
      }
    } else if (buttonBankA > 290 && buttonBankA < 330) {
      buttonChoice = REV;
    } else if (buttonBankA > 990) {
      buttonChoice = REV1;
    }

    if (buttonBankB > 30 && buttonBankB < 70) {
      buttonChoice = STOP;
    } else if (buttonBankB > 120 && buttonBankB < 160) {
      buttonChoice = FWD1;
    } else if (buttonBankB > 290 && buttonBankB < 330) {
      buttonChoice = FWD;
    } else if (buttonBankB > 990) {
      buttonChoice = SCAN;
      // myState = STATE_SCAN;
      nextPiCmd = CMD_SHOOTRAW;
    }
  }
  if (buttonBankA > 1 || buttonBankB > 1) {         // Stop reading values...
    noButtonPressed = false;
  } else if (buttonBankA < 2 && buttonBankB < 2 ) { // ...until all buttons are clearly released
    noButtonPressed = true;
  }
  return buttonChoice;
}

void i2cReceive(int howMany) {
  if (howMany >= (sizeof i2cCommand)) {
    wireReadData(i2cCommand);
    // wireReadData(i2cParameter);
    haveI2Cdata = true;
  }  // end if have enough data
}  // end of receive-ISR

void i2cRequest() {
  Wire.write(nextPiCmd);
  nextPiCmd = CMD_IDLE;
}
void tellRaspi(byte command) {
  Wire.beginTransmission(8); // This needs the Raspi's address
  wireWriteData(command);
  Wire.endTransmission();    // stop transmitting
  // delay(20);
}
