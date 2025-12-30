/*
 * Controller for the Noris based Film Scanner
 */

#include <Wire.h>

const byte SLAVE_ADDRESS = 42; // Our i2c address here
/*
i2c Setup:
The Raspi is the i2c Master (it can only be a master, and it isn't even running i2c, but SMBus.)
It polls the Arduino periodically for next thing to do, which is served by the i2cRequest() fuction, attached to the 
i2c ISR via `Wire.onRequest(i2cRequest);`in setup().

The response the Arduino sends is usually just one byte right now.
*/

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
  SCAN,   // Radio
  UPDATE  // Both A0/A1 high
};

// Define the motor states
enum MotorState {
  REV = -1,
  STOPPED,
  FWD
};

// Define the Hardware wiring
#define EYE_PIN         2 // ISR
#define FILM_END_PIN    3
#define MOTOR_B_PIN     5 // PWM
#define MOTOR_A_PIN     6 // PWM
#define TRIGGER_PIN     7
#define FAN_PIN         8
#define LAMP_PIN        9
// #define LED_PIN         unused
#define BUTTONS_A_PIN   A0
#define BUTTONS_B_PIN   A1
#define SINGLE_STEP_POT A2
#define CONT_RUN_POT    A3
#define EXPOSURE_POT    A6

enum Command
{
  CMD_NONE,

  // Arduino to Raspi
  CMD_PING,
  CMD_Z1_1,  // Zoom Leel 1:1
  CMD_Z3_1,  // Zoom Leel 3:1
  CMD_Z10_1, // Zoom Leel 6:1
  CMD_SHOOT_RAW,
  CMD_LAMP_OFF, // needs to stay at an even number
  CMD_LAMP_ON,
  CMD_INIT_SCAN, // never used?
  CMD_START_SCAN,
  CMD_STOP_SCAN,
  CMD_SET_EXP, // set new exposure time per trimpot position
  CMD_SHOW_INSERT_FILM,
  CMD_SHOW_READY_TO_SCAN,
  CMD_SET_INITVALUES, // get load state and exposure pot value (both only get send when they change)
  CMD_UPDATE_ENTER,
  CMD_UPDATE_PREV,
  CMD_UPDATE_NEXT,
  CMD_UPDATE_CONFIRM,
  CMD_UPDATE_CANCEL,

  // Raspi to Arduino
  CMD_READY = 128,
  CMD_TELL_INITVALUES, // send film load state and exposure pot value (both only get send when they change)
  CMD_TELL_LOADSTATE
};

enum ZoomMode {
  Z1_1, //  1:1
  Z3_1, //  3:1
  Z10_1 // 10:1
};


// Define some global variables
uint8_t fps18MotorPower = 0;
uint8_t singleStepMotorPower = 0;
int16_t lastExposurePot = 0;
int16_t exposurePot = 0;
// uint16_t loopCounter;
uint8_t filmLoadState;

bool lastFilmEndState;
bool filmEndState;


int dummyread; // for throw-away ADC reads (avoids multiplex-carryover of S&H cap charges)

bool lampMode = false;
bool isScanning = false;
bool updateMode = false;
uint32_t bootIgnoreUntil = 0;
uint8_t updateHoldCount = 0;
bool updateProbePrinted = false;

volatile bool piIsReady = false;

ControlButton currentButton = NONE;
ControlButton prevButton = NONE;
uint8_t currentMotor = 0;
MotorState motorState = STOPPED;
Command nextPiCmd = CMD_NONE;
ZoomMode zoomMode = Z1_1;

void setup() {
  Serial.begin(115200);

  pinMode(BUTTONS_A_PIN, INPUT);
  pinMode(BUTTONS_B_PIN, INPUT);
  pinMode(SINGLE_STEP_POT, INPUT);
  pinMode(CONT_RUN_POT, INPUT);
  pinMode(EXPOSURE_POT, INPUT);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(LAMP_PIN, OUTPUT);
  // pinMode(LED_PIN, OUTPUT);
  pinMode(MOTOR_A_PIN, OUTPUT);
  pinMode(MOTOR_B_PIN, OUTPUT);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(EYE_PIN, INPUT);
  pinMode(FILM_END_PIN, INPUT);

  bootIgnoreUntil = millis() + 800;

  // Stop the engines
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, 0);
  digitalWrite(FAN_PIN, LOW);
  digitalWrite(LAMP_PIN, LOW);

  Wire.begin(SLAVE_ADDRESS);
  Wire.onReceive(i2cReceive);
  Wire.onRequest(i2cRequest);
}

void loop() {
  bool updateCombo = updateComboActive();
  if (updateCombo) {
    if (updateHoldCount < 3) {
      updateHoldCount++;
      if (!updateProbePrinted) {
        Serial.println("Update mode: combo detected");
        updateProbePrinted = true;
      }
    }
  } else {
    updateHoldCount = 0;
    updateProbePrinted = false;
  }
  if (!updateMode && updateHoldCount >= 3) {
    updateMode = true;
    nextPiCmd = CMD_UPDATE_ENTER;
    Serial.println("Update mode: enter");
    prevButton = UPDATE;
    return;
  }
  if (!updateMode && millis() < bootIgnoreUntil) {
    currentButton = pollButtons();
    prevButton = currentButton;
    return;
  }

  if (updateMode) {
    currentButton = pollButtons();
    if (currentButton != prevButton) {
      prevButton = currentButton;
      switch (currentButton) {
        case REV1:
          nextPiCmd = CMD_UPDATE_PREV;
          break;
        case FWD1:
          nextPiCmd = CMD_UPDATE_NEXT;
          break;
        case SCAN:
          nextPiCmd = CMD_UPDATE_CONFIRM;
          break;
        case STOP:
          nextPiCmd = CMD_UPDATE_CANCEL;
          break;
        default:
          break;
      }
    }
    return;
  }

  currentButton = pollButtons();
  if (isScanning && piIsReady && nextPiCmd != CMD_STOP_SCAN)
  {
    piIsReady = false;
    if (!digitalRead(FILM_END_PIN))
    {
      Serial.println("Film ended");
      stopScanning();
    }
    else
    {
      motorFWD1();               // advance
      nextPiCmd = CMD_SHOOT_RAW; // tell to shoot
    }
  }

  // Read the trim pots to determine PWM width for the Motor
  dummyread = analogRead(CONT_RUN_POT);
  fps18MotorPower = map(analogRead(CONT_RUN_POT), 0, 1023, 255, 100); // 100 since lower values don't start the motor
  dummyread = analogRead(SINGLE_STEP_POT);
  singleStepMotorPower = map(analogRead(SINGLE_STEP_POT), 0, 1023, 255, 100);

  if (currentButton != prevButton) {
    prevButton = currentButton;

    if (!isScanning || currentButton == STOP) {
      switch (currentButton) {
        case NONE:
        default:
          break;
        case ZOOM:
          setZoomMode((zoomMode == Z10_1) ? Z1_1 : (ZoomMode)((uint8_t)zoomMode + 1));
          nextPiCmd = (Command)((uint8_t)CMD_Z1_1 + (uint8_t)zoomMode);
          break;
        case LIGHT:
          setLampMode(!lampMode);
          nextPiCmd = (Command)((uint8_t)CMD_LAMP_OFF + lampMode);
          break;
        case STOP:
          if (isScanning) {
            stopScanning();
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
          } else {
            Serial.print("< at Speed ");
            Serial.println(singleStepMotorPower);
            motorREV1();
          }
          break;
        case FWD1:
          if (motorState != STOPPED) {
            Serial.println("Motor not stopped.");
          } else {
            Serial.print("> at Speed ");
            Serial.println(singleStepMotorPower);
            motorFWD1();
          }
          break;
        case RUNFWD:
          if (motorState == REV) {
            stopBriefly();
          }
          motorState = FWD;
          Serial.print("Motor: >> at Speed ");
          Serial.println(fps18MotorPower);
          motorFwd();
          break;
        case SCAN:
          isScanning = true;
          nextPiCmd = CMD_START_SCAN;
          setLampMode(true);
          // ... (don't forget to detach ISR)
          break;
      }
    } 
  } else {
    // don't readExposurePot if a button has been pressed
    if (!isScanning) {
      readExposurePot(); // reads with some hysteresis to avoid flickering
    }
    readFilmEndSensor();
  }

  if (motorState == FWD || motorState == REV) {
    analogWrite(currentMotor, fps18MotorPower);
  }
}

void readExposurePot() {
  lastExposurePot = exposurePot;
  dummyread = analogRead(EXPOSURE_POT);
  dummyread = analogRead(EXPOSURE_POT);
  int16_t newExposurePot = analogRead(EXPOSURE_POT);
  if (abs(lastExposurePot - newExposurePot) >= 3) {
    exposurePot = newExposurePot;
    Serial.print("New Exposure Setting: ");
    Serial.println(exposurePot);
    nextPiCmd = CMD_SET_EXP;
  }
}

void readFilmEndSensor() {
  lastFilmEndState = filmEndState;
  filmEndState = digitalRead(FILM_END_PIN);
  if (filmEndState != lastFilmEndState) {
    if (filmEndState == 0) {
      nextPiCmd = CMD_SHOW_INSERT_FILM;
    } else {
      nextPiCmd = CMD_SHOW_READY_TO_SCAN;
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

  if (!mode)
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

  if (mode != Z1_1)
    setLampMode(true);

  zoomMode = mode;
  Serial.print("Zoom mode: ");
  Serial.print(zoomMode);
  Serial.print(". Telling Raspi to zoom ");
  Serial.println((zoomMode == Z1_1) ? "out" : "in");
}

void motorFWD1() {
  EIFR = 1; // clear flag for interrupt
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, FALLING);
  analogWrite(MOTOR_A_PIN, singleStepMotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorREV1() {
  EIFR = 1; // clear flag for interrupt
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, FALLING);
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, singleStepMotorPower);
}

void motorFwd() {
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
  currentMotor = MOTOR_A_PIN;
  analogWrite(MOTOR_A_PIN, fps18MotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorRev() {
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
  currentMotor = MOTOR_B_PIN;
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, fps18MotorPower);
}

void stopMotorISR() {
  motorState = STOPPED;
  digitalWrite(MOTOR_A_PIN, HIGH);
  digitalWrite(MOTOR_B_PIN, HIGH);
//  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
}

void stopScanning() {
  isScanning = false;
  piIsReady = false;
  setLampMode(false);
  zoomMode = Z1_1;
  nextPiCmd = CMD_STOP_SCAN;
}

ControlButton pollButtons() {
  static bool noButtonPressed = false;
  dummyread = analogRead(BUTTONS_A_PIN); // avoid spill-over from multiplexed ADC (discharge S&H cap)
  int buttonBankA = analogRead(BUTTONS_A_PIN); // Substract 5 since A0 tends to get noisy when other A-ins are used!?
  dummyread = analogRead(BUTTONS_B_PIN);   // avoid spill-over from multiplexed ADC (discharge S&H cap)
  int buttonBankB = analogRead(BUTTONS_B_PIN) ;
  ControlButton buttonChoice;

  delay(10); // debounce (since button release bounce is not covered in the FSM)

  if (noButtonPressed)
  {
    if (buttonBankA < 2 && buttonBankB < 2) {
      buttonChoice = NONE;

    // Button bank A
    } else if (buttonBankA > 900 && buttonBankB > 900) {
      buttonChoice = UPDATE;
    } else if (buttonBankA > 30 && buttonBankA < 70) {
      buttonChoice = REV1;    // on Vero Board: ZOOM
    } else if (buttonBankA > 120 && buttonBankA < 160) {
      buttonChoice = RUNREV;  // on Vero Board: LIGHT
    } else if (buttonBankA > 290 && buttonBankA < 330) {
      buttonChoice = ZOOM;    // on Vero Board: RUNREV
    } else if (buttonBankA > 990) {
      buttonChoice = LIGHT;   // on Vero Board: REV1

    // Button bank B
    } else if (buttonBankB > 30 && buttonBankB < 70) {
      buttonChoice = SCAN;     // on Vero Board: STOP
    } else if (buttonBankB > 120 && buttonBankB < 160) {
      buttonChoice = RUNFWD;  // on Vero Board: FWD1
    } else if (buttonBankB > 290 && buttonBankB < 330) {
      buttonChoice = FWD1;    // on Vero Board: RUNFWD
    } else if (buttonBankB > 990) {
      buttonChoice = STOP;    // on Vero Board: SCAN
    }
  }

  // Stop reading values until all buttons are clearly released
  noButtonPressed = buttonBankA < 2 && buttonBankB < 2;

  return buttonChoice;
}

bool updateComboActive() {
  dummyread = analogRead(BUTTONS_A_PIN);
  int buttonBankA = analogRead(BUTTONS_A_PIN);
  dummyread = analogRead(BUTTONS_B_PIN);
  int buttonBankB = analogRead(BUTTONS_B_PIN);
  return buttonBankA > 900 && buttonBankB > 900;
}

void i2cReceive(int howMany) {
  // This is called when the Pi tells us something (like: ready to take next photo)
  uint8_t i2cCommand;
  if (howMany >= (sizeof i2cCommand))
  {
    while (Wire.available()) {
      i2cCommand = Wire.read();
    }
    
    // Don't set piIsReady if we aren't scanning anymore
    if ((Command)i2cCommand == CMD_READY && isScanning) {
      piIsReady = true;
    }
    if ((Command)i2cCommand == CMD_TELL_INITVALUES)
    {
      filmLoadState = digitalRead(FILM_END_PIN);
      dummyread = analogRead(EXPOSURE_POT);
      exposurePot = analogRead(EXPOSURE_POT);
      Serial.print("Current Film load state: ");
      Serial.println(filmLoadState);
      Serial.print("Current Exposure Setting: ");
      Serial.println(exposurePot);
      nextPiCmd = CMD_SET_INITVALUES;
    }
  }
} 


void i2cRequest() {
  // This gets called when the Pi uses ask_arduino() in its loop to ask what to do next. 
  Wire.write(nextPiCmd);

  // Special cas ewhen the exposure pot was changed
  if (nextPiCmd == CMD_SET_EXP) {
    Serial.println("Requesting new Exposure Time value.");
    Wire.write((const uint8_t *)&exposurePot, sizeof exposurePot);  // little endian
  }

  // Special case to get initial (current) values of film load switch and exposue pot
  if (nextPiCmd == CMD_SET_INITVALUES) {
    #define INIT_VALUES_SIZE 3
    Wire.write((const uint8_t *)&exposurePot, sizeof exposurePot); // little endian
    Wire.write(filmLoadState);
  }
  nextPiCmd = CMD_NONE;
}
