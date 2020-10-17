/*
 * Controller for the Noris based Film Scanner
 *
 * Todo:
 * 
 * 
 *
 * Raspi Todos:
 * - clear screen on boot / start my python code
 * - Enable Screen before Scan:
 *    - /opt/vc/bin/tvservice -p # Display an
 * - Disable Screen after Scan:
 *    - /opt/vc/bin/tvservice -o # Display aus
 *
 *
 * - Draw Schematics already
 *
 */

#include <Wire.h>
#include <WireData.h>

const byte SLAVE_ADDRESS = 42; // Our i2c address here

// Define the Control Buttons
enum ControlButton {
  NONE,   // No Button pressed
  ZOOM,   // Toggle
  LIGHT,  // Toggle
  RUNREV, // Radio
  REV1,   // Push
  STOP,   // Radio
  FWD1,   // Push
  RUNFWD, // Radio
  SCAN    // Radio
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

enum Command {
// Arduino to Raspi
  CMD_IDLE,
  CMD_PING,
  CMD_ZOOM_CYCLE,
  CMD_SHOOT_RAW,
  CMD_LAMP_ON,
  CMD_LAMP_OFF,
  CMD_INIT_SCAN,
  CMD_START_SCAN,
  CMD_STOP_SCAN,

// Raspi to Arduino
  CMD_READY = 128
} nextPiCmd = CMD_IDLE;

enum ZoomMode {
  Z1_1, //  1:1
  Z3_1, //  3:1
  Z10_1 // 10:1
} zoomMode = Z1_1;

// Define some constants
uint8_t  fps18MotorPower;
uint8_t  singleStepMotorPower;

// Define some global variables
bool    lampMode = false;
bool    isScanning = false;
uint8_t ISRcount = 0;
uint8_t speed = 0;

volatile bool piIsReady = false;

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
  if (isScanning && piIsReady) {
    piIsReady = false;
    motorFWD1();                // advance
    nextPiCmd = CMD_SHOOT_RAW;  // tell to shoot
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
          setZoomMode((zoomMode == Z10_1) ? Z1_1 : (ZoomMode)((uint8_t)zoomMode + 1));
          nextPiCmd = CMD_ZOOM_CYCLE;
          break;
        case LIGHT:
          setLampMode(!lampMode);
          nextPiCmd = lampMode ? CMD_LAMP_OFF : CMD_LAMP_ON;
          break;
        case STOP:
          if (isScanning) {
            setLampMode(false);
            if (isScanning) {
              isScanning = false;
              nextPiCmd = CMD_STOP_SCAN;
            }
            Serial.println("Scanning mode: 0");
          } else {
            stopMotor();
          }
          break;
        case RUNREV:
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
          if (motorState != STOPPED) {
            Serial.println("Motor not stopped.");
            break;
          }
          Serial.print("> at Speed ");
          Serial.println(singleStepMotorPower);
          motorFWD1();
          break;
        case RUNFWD:
          if (motorState == REV)
            stopBriefly();
          motorState = FWD;
          Serial.print("Motor: >> at Speed ");
          Serial.println(fps18MotorPower);
          motorFwd();
          break;
        case SCAN:
          if (!isScanning) {
            if (motorState != STOPPED)
              stopBriefly();
              
            setZoomMode(Z1_1);
            setLampMode(true);
            isScanning = true;
            nextPiCmd = CMD_START_SCAN;
          }
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
  if (!mode && zoomMode != Z1_1)
    setZoomMode(Z1_1);
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

void setZoomMode(ZoomMode mode) {
  if (mode == zoomMode)
    return;
  if (mode != Z1_1 && !lampMode)
    setLampMode(true);

  zoomMode = mode;
  Serial.print("Zoom mode: ");
  Serial.print(zoomMode);
  Serial.print(". Telling Raspi to zoom ");
  Serial.println((zoomMode == Z1_1) ? "out" : "in");
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
    } else if (buttonBankA > 120 && buttonBankA < 160) {
      buttonChoice = LIGHT;
    } else if (buttonBankA > 290 && buttonBankA < 330) {
      buttonChoice = RUNREV;
    } else if (buttonBankA > 990) {
      buttonChoice = REV1;
    }

    if (buttonBankB > 30 && buttonBankB < 70) {
      buttonChoice = STOP;
    } else if (buttonBankB > 120 && buttonBankB < 160) {
      buttonChoice = FWD1;
    } else if (buttonBankB > 290 && buttonBankB < 330) {
      buttonChoice = RUNFWD;
    } else if (buttonBankB > 990) {
      buttonChoice = SCAN;
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
  uint8_t i2cCommand;
  if (howMany >= (sizeof i2cCommand)) {
    wireReadData(i2cCommand);

    // Don't set piIsReady if we aren't scanning anymore
    if ((Command)i2cCommand == CMD_READY && isScanning) {
      piIsReady = true;
    }
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
