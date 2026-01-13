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
  SCAN    // Radio
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
  CMD_PAIRING_ENTER,
  CMD_PAIRING_EXIT,
  CMD_PAIRING_CANCEL,
  CMD_LOGS_ENTER,
  CMD_LOGS_EXIT,
  CMD_UNPAIR_ENTER,
  CMD_AWB_ENTER,
  CMD_AWB_PREV,
  CMD_AWB_NEXT,
  CMD_AWB_CONFIRM,
  CMD_AWB_CANCEL,
  CMD_MENU_ENTER,
  CMD_MENU_EXIT,
  CMD_MENU_PREV,
  CMD_MENU_NEXT,
  CMD_MENU_SELECT,

  // Raspi to Arduino
  CMD_READY = 128,
  CMD_TELL_INITVALUES, // send film load state and exposure pot value (both only get send when they change)
  CMD_TELL_LOADSTATE,
  CMD_AWB_EXIT
};

enum ZoomMode {
  Z1_1, //  1:1
  Z3_1, //  3:1
  Z10_1 // 10:1
};

enum MenuState {
  MENU_IDLE,      // Normal operation
  MENU_MAIN,      // Main settings menu
  MENU_UPDATE,    // Firmware update submenu
  MENU_PAIRING,   // Pairing submenu
  MENU_AWB,       // White balance submenu
  MENU_LOGS,      // Debug log submenu
  MENU_UNPAIR     // Factory reset submenu
};

enum MenuItem {
  MENU_ITEM_UPDATE = 0,
  MENU_ITEM_PAIRING = 1,
  MENU_ITEM_AWB = 2,
  MENU_ITEM_LOGS = 3,
  MENU_ITEM_UNPAIR = 4,
  MENU_ITEM_COUNT = 5
};


// Define some global variables
uint8_t fps18MotorPower = 0;
uint8_t singleStepMotorPower = 0;
int16_t exposurePot = 0;
int16_t lastSentExposurePot = -100;  // last value sent to Pi (init far away to trigger first send)
// uint16_t loopCounter;
uint8_t filmLoadState;

bool lastFilmEndState;
bool filmEndState;
bool filmEndLowPending = false;
uint32_t filmEndLowSince = 0;


int dummyread; // for throw-away ADC reads (avoids multiplex-carryover of S&H cap charges)

bool lampMode = false;
bool isScanning = false;
uint8_t scanExtraFrames = 0;  // frames to continue after film end detected
uint8_t filmEjectAdvances = 0;  // advances to eject film after scanning done
volatile bool singleStepInProgress = false;  // true while single-step motor advance is running
uint8_t scanFilmEndCount = 0;  // consecutive film-end reads needed to trigger end-of-roll
bool updateMode = false;
bool pairingMode = false;
bool logsMode = false;
bool awbMode = false;
uint32_t pairingModeEnteredAt = 0;
bool pairingCancelPending = false;
uint32_t pairingCancelSentAt = 0;
uint32_t bootIgnoreUntil = 0;

// Menu system
MenuState menuState = MENU_IDLE;
uint8_t menuSelected = 0;  // Current selection in main menu
bool stopButtonPressed = false;
uint32_t stopButtonPressedAt = 0;
const uint32_t STOP_LONG_PRESS_MS = 4000;  // 4 seconds

volatile bool piIsReady = false;

ControlButton currentButton = NONE;
ControlButton prevButton = NONE;
uint8_t currentMotor = 0;
MotorState motorState = STOPPED;
Command nextPiCmd = CMD_NONE;
ZoomMode zoomMode = Z1_1;

void setup() {
  // Immediately disable lamp to prevent brief flash during boot
  pinMode(LAMP_PIN, OUTPUT);
  digitalWrite(LAMP_PIN, LOW);

  Serial.begin(115200);

  pinMode(BUTTONS_A_PIN, INPUT);
  pinMode(BUTTONS_B_PIN, INPUT);
  pinMode(SINGLE_STEP_POT, INPUT);
  pinMode(CONT_RUN_POT, INPUT);
  pinMode(EXPOSURE_POT, INPUT);
  pinMode(FAN_PIN, OUTPUT);
  // pinMode(LED_PIN, OUTPUT);
  pinMode(MOTOR_A_PIN, OUTPUT);
  pinMode(MOTOR_B_PIN, OUTPUT);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(EYE_PIN, INPUT);
  pinMode(FILM_END_PIN, INPUT);

  // Initialize film end state to current value to prevent spurious state change detection
  filmEndState = digitalRead(FILM_END_PIN);
  lastFilmEndState = filmEndState;

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
  if (!updateMode && millis() < bootIgnoreUntil) {
    currentButton = pollButtons();
    prevButton = currentButton;
    return;
  }

  // Handle menu system
  if (menuState != MENU_IDLE) {
    handleMenuSystem();
    return;
  }

  // Check for long-press STOP button to enter menu (only when idle/ready)
  // We need to check raw ADC value directly, not pollButtons(), because pollButtons()
  // only detects edge transitions and won't continuously return STOP while held
  // Only check for long-press if we're truly idle (not scanning, motor stopped, no single step)
  if (!isScanning && motorState == STOPPED && !singleStepInProgress) {
    dummyread = analogRead(BUTTONS_B_PIN);
    int buttonBankB = analogRead(BUTTONS_B_PIN);
    bool stopButtonCurrentlyPressed = (buttonBankB > 990);  // STOP button threshold
    
    if (stopButtonCurrentlyPressed) {
      if (!stopButtonPressed) {
        // Button just pressed - start timing
        stopButtonPressed = true;
        stopButtonPressedAt = millis();
        Serial.println("Menu: STOP button pressed, timing...");
      } else {
        // Button still held - check if long enough
        uint32_t pressDuration = millis() - stopButtonPressedAt;
        if (pressDuration >= STOP_LONG_PRESS_MS) {
          // Long press detected - enter menu immediately
          menuState = MENU_MAIN;
          menuSelected = 0;
          stopButtonPressed = false;
          prevButton = NONE;  // Reset prevButton so menu navigation works
          currentButton = NONE;  // Reset currentButton
          nextPiCmd = CMD_MENU_ENTER;
          Serial.println("Menu: enter (long press STOP)");
          return;
        }
      }
    } else {
      // Button not pressed or released
      if (stopButtonPressed) {
        // Button was pressed but released before long-press threshold
        uint32_t pressDuration = millis() - stopButtonPressedAt;
        Serial.print("Menu: STOP released after ");
        Serial.print(pressDuration);
        Serial.println(" ms (too short)");
        // Reset button state so pollButtons() can detect the release and handle it normally
        stopButtonPressed = false;
        // Reset prevButton so the button release can be detected by normal handler
        prevButton = NONE;
      } else {
        stopButtonPressed = false;
      }
    }
  } else {
    // Not idle - reset long-press state
    stopButtonPressed = false;
  }

  if (updateMode || pairingMode || logsMode || awbMode) {
    if (pairingMode) {
      dummyread = analogRead(BUTTONS_B_PIN);
      int pairingButtonsB = analogRead(BUTTONS_B_PIN);
      currentButton = pollButtons();
      if (pairingButtonsB > 990 || currentButton == STOP) {
        Serial.println("Pairing mode: stop pressed");
        pairingMode = false;
        pairingCancelPending = true;
        pairingCancelSentAt = millis();
        nextPiCmd = CMD_PAIRING_CANCEL;
      } else if ((millis() - pairingModeEnteredAt) > 130000) {
        pairingMode = false;
        nextPiCmd = CMD_NONE;
      }
      return;
    }
    if (updateMode) {
      currentButton = pollButtons();
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            nextPiCmd = CMD_UPDATE_PREV;
            break;
          case RUNFWD:
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
    }
    if (awbMode) {
      currentButton = pollButtons();
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            nextPiCmd = CMD_AWB_PREV;
            break;
          case RUNFWD:
            nextPiCmd = CMD_AWB_NEXT;
            break;
          case SCAN:
            nextPiCmd = CMD_AWB_CONFIRM;
            break;
          case STOP:
            nextPiCmd = CMD_AWB_CANCEL;
            break;
          default:
            break;
        }
      }
    }
    return;
  }

  if (pairingCancelPending) {
    return;
  }

  currentButton = pollButtons();
  if (isScanning && piIsReady && nextPiCmd != CMD_STOP_SCAN)
  {
    piIsReady = false;
    if (!digitalRead(FILM_END_PIN))
    {
      if (scanExtraFrames == 0)
      {
        scanFilmEndCount++;
        if (scanFilmEndCount >= 3)  // require 3 consecutive film-end reads
        {
          // Film end confirmed - start countdown to scan film remainder
          scanExtraFrames = 25;
          Serial.println("Film ended - scanning 25 extra frames");
        }
      }
    }
    else
    {
      scanFilmEndCount = 0;  // reset counter if film is detected
    }
    
    if (scanExtraFrames > 0)
    {
      scanExtraFrames--;
      if (scanExtraFrames == 0)
      {
        Serial.println("Extra frames done - stopping scan, ejecting film");
        stopScanning();
        filmEjectAdvances = 15;  // start eject phase
        motorFWD1();  // start first eject advance
      }
      else
      {
        motorFWD1();               // advance
        nextPiCmd = CMD_SHOOT_RAW; // tell to shoot
      }
    }
    else
    {
      motorFWD1();               // advance
      nextPiCmd = CMD_SHOOT_RAW; // tell to shoot
    }
  }

  // Handle film eject advances (after scan ends)
  if (filmEjectAdvances > 0 && !singleStepInProgress)
  {
    filmEjectAdvances--;
    if (filmEjectAdvances > 0)
    {
      motorFWD1();  // next eject advance
    }
    else
    {
      Serial.println("Film eject complete");
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
        case STOP:
          // Only trigger normal STOP action if we're not actively timing a long-press
          // If stopButtonPressed is true, we're timing a long-press, so don't trigger normal action
          // The long-press handler will either enter menu (if held long enough) or do nothing
          // Note: stopButtonPressed is reset when button is released, so normal STOP will work after release
          if (!stopButtonPressed) {
            if (isScanning) {
              stopScanning();
            } else {
              stopMotor();
            }
          } else {
            // We're timing a long-press, but user released before threshold
            // The long-press handler will reset stopButtonPressed, so next press will work
            Serial.println("STOP: ignoring (long-press timing)");
          }
          break;
        case ZOOM:
          setZoomMode((zoomMode == Z10_1) ? Z1_1 : (ZoomMode)((uint8_t)zoomMode + 1));
          nextPiCmd = (Command)((uint8_t)CMD_Z1_1 + (uint8_t)zoomMode);
          break;
        case LIGHT:
          setLampMode(!lampMode);
          nextPiCmd = (Command)((uint8_t)CMD_LAMP_OFF + lampMode);
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
          if (motorState != STOPPED || singleStepInProgress) {
            Serial.println("Motor not stopped.");
          } else {
            Serial.print("< at Speed ");
            Serial.println(singleStepMotorPower);
            motorREV1();
          }
          break;
        case FWD1:
          if (motorState != STOPPED || singleStepInProgress) {
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
          scanExtraFrames = 0;  // reset extra frames counter
          scanFilmEndCount = 0;  // reset film end debounce counter
          filmEjectAdvances = 0;  // cancel any pending eject
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
      readFilmEndSensor();  // only check film end when not scanning
    }
  }

  if (motorState == FWD || motorState == REV) {
    analogWrite(currentMotor, fps18MotorPower);
  }
}

void readExposurePot() {
  dummyread = analogRead(EXPOSURE_POT);
  dummyread = analogRead(EXPOSURE_POT);
  int16_t newExposurePot = analogRead(EXPOSURE_POT);
  // Compare against last SENT value to avoid drift-triggered updates
  if (abs(lastSentExposurePot - newExposurePot) >= 8) {
    exposurePot = newExposurePot;
    lastSentExposurePot = newExposurePot;
    Serial.print("New Exposure Setting: ");
    Serial.println(exposurePot);
    nextPiCmd = CMD_SET_EXP;
  }
}

void readFilmEndSensor() {
  lastFilmEndState = filmEndState;
  filmEndState = digitalRead(FILM_END_PIN);
  if (filmEndState == 0) {
    if (lastFilmEndState != 0) {
      filmEndLowSince = millis();
      filmEndLowPending = true;
    }
    if (filmEndLowPending && (millis() - filmEndLowSince) >= 500) {
      // Stop motor if running continuously (RUNFWD/RUNREV) and film was inserted
      if (motorState == FWD || motorState == REV) {
        Serial.println("Film ended during continuous run - stopping");
        stopMotor();
      }
      nextPiCmd = CMD_SHOW_INSERT_FILM;
      filmEndLowPending = false;
    }
  } else {
    filmEndLowPending = false;
    if (lastFilmEndState != 1) {
      nextPiCmd = CMD_SHOW_READY_TO_SCAN;
    }
  }
}

void handleMenuSystem() {
  currentButton = pollButtons();
  
  if (menuState == MENU_MAIN) {
    // Main menu navigation
    if (currentButton != prevButton) {
      Serial.print("Menu: button changed from ");
      Serial.print(prevButton);
      Serial.print(" to ");
      Serial.println(currentButton);
      prevButton = currentButton;
      switch (currentButton) {
        case REV1:
          // Navigate up (wrap around)
          menuSelected = (menuSelected - 1 + MENU_ITEM_COUNT) % MENU_ITEM_COUNT;
          nextPiCmd = CMD_MENU_PREV;
          Serial.print("Menu: selected item ");
          Serial.println(menuSelected);
          break;
        case FWD1:
          // Navigate down (wrap around)
          menuSelected = (menuSelected + 1) % MENU_ITEM_COUNT;
          nextPiCmd = CMD_MENU_NEXT;
          Serial.print("Menu: selected item ");
          Serial.println(menuSelected);
          break;
        case RUNFWD:
          // Enter selected menu item
          nextPiCmd = CMD_MENU_SELECT;
          Serial.print("Menu: entering item ");
          Serial.println(menuSelected);
          switch ((MenuItem)menuSelected) {
            case MENU_ITEM_UPDATE:
              menuState = MENU_UPDATE;
              updateMode = true;
              nextPiCmd = CMD_UPDATE_ENTER;
              break;
            case MENU_ITEM_PAIRING:
              menuState = MENU_PAIRING;
              pairingMode = true;
              pairingModeEnteredAt = millis();
              nextPiCmd = CMD_PAIRING_ENTER;
              break;
            case MENU_ITEM_AWB:
              menuState = MENU_AWB;
              awbMode = true;
              nextPiCmd = CMD_AWB_ENTER;
              break;
            case MENU_ITEM_LOGS:
              menuState = MENU_LOGS;
              logsMode = true;
              nextPiCmd = CMD_LOGS_ENTER;
              break;
            case MENU_ITEM_UNPAIR:
              menuState = MENU_UNPAIR;
              nextPiCmd = CMD_UNPAIR_ENTER;
              break;
            default:
              break;
          }
          break;
        case RUNREV:
          // Exit menu
          menuState = MENU_IDLE;
          nextPiCmd = CMD_MENU_EXIT;
          Serial.println("Menu: exit");
          break;
        default:
          break;
      }
    }
  } else {
    // Handle submenu modes (update, pairing, awb, logs, unpair)
    // Note: currentButton already set at start of handleMenuSystem() - don't call pollButtons() again!
    if (updateMode) {
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            // Go back to main menu
            menuState = MENU_MAIN;
            updateMode = false;
            nextPiCmd = CMD_UPDATE_CANCEL;
            Serial.println("Update: back to menu");
            break;
          case REV1:
            nextPiCmd = CMD_UPDATE_PREV;
            Serial.println("Update: prev");
            break;
          case FWD1:
            nextPiCmd = CMD_UPDATE_NEXT;
            Serial.println("Update: next");
            break;
          case RUNFWD:
            nextPiCmd = CMD_UPDATE_CONFIRM;
            Serial.println("Update: confirm");
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            updateMode = false;
            nextPiCmd = CMD_UPDATE_CANCEL;
            Serial.println("Update: exit menu");
            // Note: Python will need to detect menu exit via menuState change
            // We'll send CMD_MENU_EXIT on next i2c request if menuState is IDLE
            break;
          default:
            break;
        }
      }
    } else if (pairingMode) {
      dummyread = analogRead(BUTTONS_B_PIN);
      int pairingButtonsB = analogRead(BUTTONS_B_PIN);
      // Note: currentButton already set at start of handleMenuSystem() - don't call pollButtons() again!
      if (pairingButtonsB > 990 || currentButton == STOP) {
        Serial.println("Pairing mode: stop pressed");
        menuState = MENU_MAIN;
        pairingMode = false;
        pairingCancelPending = true;
        pairingCancelSentAt = millis();
        nextPiCmd = CMD_PAIRING_CANCEL;
      } else if (currentButton == RUNREV) {
        // Go back to main menu
        menuState = MENU_MAIN;
        pairingMode = false;
        nextPiCmd = CMD_PAIRING_CANCEL;
        Serial.println("Pairing: back to menu");
      } else if ((millis() - pairingModeEnteredAt) > 130000) {
        menuState = MENU_MAIN;
        pairingMode = false;
        nextPiCmd = CMD_NONE;
      }
    } else if (awbMode) {
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            // Go back to main menu
            menuState = MENU_MAIN;
            awbMode = false;
            nextPiCmd = CMD_AWB_CANCEL;
            Serial.println("AWB: back to menu");
            break;
          case REV1:
            nextPiCmd = CMD_AWB_PREV;
            break;
          case FWD1:
            nextPiCmd = CMD_AWB_NEXT;
            break;
          case RUNFWD:
            nextPiCmd = CMD_AWB_CONFIRM;
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            awbMode = false;
            nextPiCmd = CMD_AWB_CANCEL;
            Serial.println("AWB: exit menu");
            break;
          default:
            break;
        }
      }
    } else if (logsMode) {
      currentButton = pollButtons();
      if (currentButton != prevButton) {
        prevButton = currentButton;
        if (currentButton == RUNREV || currentButton == STOP) {
          // Go back to main menu or exit
          menuState = MENU_MAIN;
          logsMode = false;
          nextPiCmd = CMD_LOGS_EXIT;
          Serial.println("Logs: back to menu");
        }
      }
    } else if (menuState == MENU_UNPAIR) {
      currentButton = pollButtons();
      if (currentButton != prevButton) {
        prevButton = currentButton;
        if (currentButton == RUNREV || currentButton == STOP) {
          // Go back to main menu or exit
          menuState = MENU_MAIN;
          nextPiCmd = CMD_NONE;
          Serial.println("Unpair: back to menu");
        }
      }
    }
  }
}


void stopMotor() {
  // ...
  motorState = STOPPED;
  singleStepInProgress = false;
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
  singleStepInProgress = true;
  EIFR = 1; // clear flag for interrupt
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, FALLING);
  analogWrite(MOTOR_A_PIN, singleStepMotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorREV1() {
  singleStepInProgress = true;
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
  singleStepInProgress = false;
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
  ControlButton buttonChoice = NONE;

  delay(10); // debounce (since button release bounce is not covered in the FSM)

  if (noButtonPressed)
  {
    if (buttonBankA < 2 && buttonBankB < 2) {
      buttonChoice = NONE;

    // Button bank A
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

void i2cReceive(int howMany) {
  // This is called when the Pi tells us something (like: ready to take next photo)
  uint8_t i2cCommand;
  if (howMany >= (sizeof i2cCommand))
  {
    while (Wire.available()) {
      i2cCommand = Wire.read();
    }
    
    if ((Command)i2cCommand == CMD_PAIRING_EXIT) {
      pairingMode = false;
      menuState = MENU_MAIN;
      nextPiCmd = CMD_NONE;
      pairingCancelPending = false;
    }
    if ((Command)i2cCommand == CMD_LOGS_EXIT) {
      logsMode = false;
      menuState = MENU_MAIN;
      nextPiCmd = CMD_NONE;
    }
    if ((Command)i2cCommand == CMD_AWB_EXIT) {
      awbMode = false;
      menuState = MENU_MAIN;
      nextPiCmd = CMD_NONE;
      Serial.println("AWB menu: exit");
    }
    if ((Command)i2cCommand == CMD_MENU_EXIT) {
      menuState = MENU_IDLE;
      nextPiCmd = CMD_NONE;
      Serial.println("Menu: exit (from Pi)");
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
  Command cmdToSend = nextPiCmd;
  Wire.write(cmdToSend);

  if (pairingCancelPending && (millis() - pairingCancelSentAt) > 5000) {
    pairingCancelPending = false;
  }

  // Special case when the exposure pot was changed
  if (cmdToSend == CMD_SET_EXP) {
    Serial.println("Sending new Exposure Time value.");
    Wire.write((const uint8_t *)&exposurePot, sizeof exposurePot);  // little endian
  }

  // Special case to get initial (current) values of film load switch and exposue pot
  if (cmdToSend == CMD_SET_INITVALUES) {
    #define INIT_VALUES_SIZE 3
    Wire.write((const uint8_t *)&exposurePot, sizeof exposurePot); // little endian
    Wire.write(filmLoadState);
  }
  if (pairingCancelPending && cmdToSend == CMD_PAIRING_CANCEL) {
    nextPiCmd = CMD_PAIRING_CANCEL;
  } else if (cmdToSend == CMD_UPDATE_CANCEL && menuState == MENU_IDLE) {
    // If we just canceled update and menu is now IDLE, send MENU_EXIT next
    // so Python knows to exit menu mode
    nextPiCmd = CMD_MENU_EXIT;
  } else {
    nextPiCmd = CMD_NONE;
  }
}
