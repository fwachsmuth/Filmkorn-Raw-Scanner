/*
 * Controller for the Noris based Film Scanner
 */

#include <avr/io.h>
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
#define FAN_PIN         8
#define LAMP_PIN        9
// #define LED_PIN         unused
#define BUTTONS_A_PIN   A0
#define BUTTONS_B_PIN   A1
#define SINGLE_STEP_POT A2
#define CONT_RUN_POT    A3
#define EXPOSURE_POT    A6
#define REV_PIN         A7   // Board revision: voltage divider 10k to GND, R51 (VCC to A7) per revision

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
  CMD_UNPAIR_PREV,
  CMD_UNPAIR_NEXT,
  CMD_UNPAIR_CONFIRM,
  CMD_UNPAIR_CANCEL,
  CMD_AWB_ENTER = 30,
  CMD_AWB_PREV = 31,
  CMD_AWB_NEXT = 32,
  CMD_AWB_CONFIRM = 33,
  CMD_AWB_CANCEL = 34,
  CMD_TARGET_ENTER = 35,
  CMD_TARGET_PREV = 36,
  CMD_TARGET_NEXT = 37,
  CMD_TARGET_CONFIRM = 38,
  CMD_TARGET_CANCEL = 39,
  CMD_MENU_ENTER = 40,
  CMD_MENU_EXIT = 41,
  CMD_MENU_PREV = 42,
  CMD_MENU_NEXT = 43,
  CMD_MENU_SELECT = 44,
  CMD_WIFI_ENTER = 45,
  CMD_WIFI_PREV = 46,
  CMD_WIFI_NEXT = 47,
  CMD_WIFI_CONFIRM = 48,
  CMD_WIFI_CANCEL = 49,

  // Raspi to Arduino
  CMD_READY = 128,
  CMD_TELL_INITVALUES = 129, // send film load state and exposure pot value (both only get send when they change)
  CMD_TELL_LOADSTATE = 130,
  CMD_AWB_EXIT = 131,
  CMD_TARGET_EXIT = 132,
  CMD_TARGET_REENTER = 133,  // Re-enter target mode (used when returning from validation error)
  CMD_WIFI_EXIT = 134,
  CMD_SCAN_REJECTED = 135    // Pi rejected START_SCAN (e.g. no drive / not paired)
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
  MENU_TARGET,    // Scan target submenu
  MENU_WIFI,      // WiFi setup submenu
  MENU_LOGS,      // Debug log submenu
  MENU_UNPAIR     // Factory reset submenu
};

enum MenuItem {
  MENU_ITEM_UPDATE = 0,
  MENU_ITEM_PAIRING = 1,
  MENU_ITEM_AWB = 2,
  MENU_ITEM_TARGET = 3,
  MENU_ITEM_WIFI = 4,
  MENU_ITEM_LOGS = 5,
  MENU_ITEM_UNPAIR = 6,
  MENU_ITEM_COUNT = 7
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
uint32_t fwdFilmInsertedSince = 0;  // when film first seen inserted in RUNFWD (0 = not yet; film-end stop only after 30s)


int dummyread; // for throw-away ADC reads (avoids multiplex-carryover of S&H cap charges)

bool lampMode = false;
bool lampModeBeforeScan = false;  // saved on SCAN entry, restored on SCAN_REJECTED
bool isScanning = false;
uint8_t scanExtraFrames = 0;  // frames to continue after film end detected
uint8_t filmEjectAdvances = 0;  // advances to eject film after scanning done
volatile bool singleStepInProgress = false;  // true while single-step motor advance is running
uint8_t scanFilmEndCount = 0;  // consecutive film-end reads needed to trigger end-of-roll
bool updateMode = false;
bool pairingMode = false;
bool logsMode = false;
bool awbMode = false;
bool targetMode = false;
bool wifiMode = false;
volatile bool targetReenterPending = false;
uint32_t pairingModeEnteredAt = 0;
bool pairingCancelPending = false;
uint32_t pairingCancelSentAt = 0;
uint32_t bootIgnoreUntil = 0;

// Menu system
MenuState menuState = MENU_IDLE;
uint8_t menuSelected = 0;  // Current selection in main menu
bool stopButtonPressed = false;
uint32_t stopButtonPressedAt = 0;
const uint32_t STOP_LONG_PRESS_MS = 3000;  // 3 seconds

volatile bool piIsReady = false;

/*
 * Board revision is encoded on A7 via voltage divider: 10 kOhm to GND, R51 (VCC to A7) per revision.
 * 3.3 V reference. If A7 is floating (no R51), readings are unstable → report Rev. D.
 * E24 values for R51 per revision (Rev E = first released with this identifier):
 * Revisions:
 * E: 0 R (short)
 * F: 330 R
 * G: 1.1 k
 * H: 2.0 k
 * I: 3.0 k
 * J: 4.3 k
 * K: 5.6 k
 * L: 7.5 k
 * M: 10 k
 * N: 13 k 
 * O: 18 k 
 * P: 24 k, Q: 33 k, R: 56 k, Rev S: not populated (open).
 */
void readAndPrintBoardRevision() {
  const int numSamples = 8;
  const int maxSpread = 120;   // if (max - min) > this, consider A7 floating
  dummyread = analogRead(EXPOSURE_POT);
  int v0 = analogRead(REV_PIN);
  int sum = v0;
  int vmin = v0, vmax = v0;
  for (int i = 1; i < numSamples; i++) {
    dummyread = analogRead(REV_PIN);
    int v = analogRead(REV_PIN);
    sum += v;
    if (v < vmin) vmin = v;
    if (v > vmax) vmax = v;
  }
  int mean = sum / numSamples;
  if (vmax - vmin > maxSpread) {
    Serial.println(F("Rev. D (floating)"));
    return;
  }
  // 15 bands: E (highest ADC) .. S (lowest). Thresholds are lower bounds for each rev.
  static const uint16_t revThresholds[] = { 970, 905, 840, 775, 710, 645, 580, 515, 450, 385, 320, 255, 190, 125, 60 };
  const char revLetters[] = { 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S' };
  int rev = 0;
  while (rev < 14 && mean < (int)revThresholds[rev + 1])
    rev++;
  Serial.print(F("Rev. "));
  Serial.println(revLetters[rev]);
}

ControlButton currentButton = NONE;
ControlButton prevButton = NONE;
uint8_t currentMotor = 0;
MotorState motorState = STOPPED;
Command nextPiCmd = CMD_NONE;
ZoomMode zoomMode = Z1_1;

void setup() {  
  // Capture reset cause before any init clears it; then clear MCUSR for next reset.
  uint8_t mcusr = MCUSR;
  MCUSR = 0;

  // Immediately disable lamp to prevent brief flash during boot
  pinMode(LAMP_PIN, OUTPUT);
  digitalWrite(LAMP_PIN, LOW);

  Serial.begin(115200);
  Serial.print(F("BOOT MCUSR=0x"));
  Serial.print(mcusr, HEX);
  Serial.print(F(" PORF="));
  Serial.print((mcusr & 0x01) ? 1 : 0);  /* power-on */
  Serial.print(F(" EXTRF="));
  Serial.print((mcusr & 0x02) ? 1 : 0);  /* external reset */
  Serial.print(F(" BORF="));
  Serial.print((mcusr & 0x04) ? 1 : 0);  /* brown-out */
  Serial.print(F(" WDRF="));
  Serial.println((mcusr & 0x08) ? 1 : 0);  /* watchdog */

  pinMode(BUTTONS_A_PIN, INPUT);
  pinMode(BUTTONS_B_PIN, INPUT);
  pinMode(SINGLE_STEP_POT, INPUT);
  pinMode(CONT_RUN_POT, INPUT);
  pinMode(EXPOSURE_POT, INPUT);
  pinMode(FAN_PIN, OUTPUT);
  // pinMode(LED_PIN, OUTPUT);
  pinMode(MOTOR_A_PIN, OUTPUT);
  pinMode(MOTOR_B_PIN, OUTPUT);
  pinMode(EYE_PIN, INPUT);
  pinMode(FILM_END_PIN, INPUT);
  pinMode(REV_PIN, INPUT);

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

  readAndPrintBoardRevision();
}

void loop() {
  if (!updateMode && millis() < bootIgnoreUntil) {
    currentButton = pollButtons();
    prevButton = currentButton;
    return;
  }

  // Handle deferred target re-enter from i2cReceive ISR
  if (targetReenterPending) {
    targetReenterPending = false;
    // Python is telling us to enter target mode (e.g., due to network failure)
    // This can be called from MENU_IDLE, so we need to enter menu mode first
    if (menuState == MENU_IDLE) {
      menuState = MENU_MAIN;
      Serial.println(F("Target: entering menu mode first"));
    }
    targetMode = true;
    menuState = MENU_TARGET;
    nextPiCmd = CMD_NONE;
    // Poll buttons immediately to sync state - this prevents any button that was
    // pressed before entering menu mode from triggering actions
    currentButton = pollButtons();
    prevButton = currentButton;
    Serial.print(F("Target menu: re-enter (from Pi), menuState="));
    Serial.print(menuState);
    Serial.print(F(", targetMode="));
    Serial.println(targetMode);
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
        Serial.println(F("Menu: STOP button pressed, timing..."));
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
          Serial.println(F("Menu: enter (long press STOP)"));
          return;
        }
      }
    } else {
      // Button not pressed or released
      if (stopButtonPressed) {
        // Button was pressed but released before long-press threshold
        uint32_t pressDuration = millis() - stopButtonPressedAt;
        Serial.print(F("Menu: STOP released after "));
        Serial.print(pressDuration);
        Serial.println(F(" ms (too short)"));
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
        Serial.println(F("Pairing mode: stop pressed"));
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
          Serial.println(F("Film ended - scanning 25 extra frames"));
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
        Serial.println(F("Extra frames done - stopping scan, ejecting film"));
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
      Serial.println(F("Film eject complete"));
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
            Serial.println(F("STOP: ignoring (long-press timing)"));
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
          Serial.print(F("Motor: << at Speed "));
          Serial.println(fps18MotorPower);
          motorRev();
          break;
        case REV1:
          if (motorState != STOPPED || singleStepInProgress) {
            Serial.println(F("Motor not stopped."));
          } else {
            Serial.print(F("< at Speed "));
            Serial.println(singleStepMotorPower);
            motorREV1();
          }
          break;
        case FWD1:
          if (motorState != STOPPED || singleStepInProgress) {
            Serial.println(F("Motor not stopped."));
          } else {
            Serial.print(F("> at Speed "));
            Serial.println(singleStepMotorPower);
            motorFWD1();
          }
          break;
        case RUNFWD:
          if (motorState == REV) {
            stopBriefly();
          }
          motorState = FWD;
          // Start 30s countdown only if film is present now; else 0 until we see film in readFilmEndSensor (avoids stale value from previous run)
          fwdFilmInsertedSince = (digitalRead(FILM_END_PIN) == 1) ? millis() : 0;
          Serial.print(F("Motor: >> at Speed "));
          Serial.println(fps18MotorPower);
          motorFwd();
          break;
        case SCAN:
          lampModeBeforeScan = lampMode;
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
    Serial.print(F("New Exposure Setting: "));
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
      // Stop motor if running continuously: RUNREV always; RUNFWD only after 30s since film was first inserted
      if (motorState == REV) {
        Serial.println(F("Film ended during continuous run - stopping"));
        stopMotor();
      } else if (motorState == FWD && fwdFilmInsertedSince != 0 && (millis() - fwdFilmInsertedSince) >= 30000) {
        Serial.println(F("Film ended during continuous run - stopping"));
        stopMotor();
      }
      nextPiCmd = CMD_SHOW_INSERT_FILM;
      filmEndLowPending = false;
    }
  } else {
    filmEndLowPending = false;
    // First time film seen inserted while in RUNFWD: start 30s countdown (film-end stop only after that)
    if (motorState == FWD && fwdFilmInsertedSince == 0) {
      fwdFilmInsertedSince = millis();
    }
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
      Serial.print(F("Menu: button changed from "));
      Serial.print(prevButton);
      Serial.print(F(" to "));
      Serial.println(currentButton);
      prevButton = currentButton;
      switch (currentButton) {
        case REV1:
          // Navigate up (wrap around)
          menuSelected = (menuSelected - 1 + MENU_ITEM_COUNT) % MENU_ITEM_COUNT;
          nextPiCmd = CMD_MENU_PREV;
          Serial.print(F("Menu: selected item "));
          Serial.println(menuSelected);
          break;
        case FWD1:
          // Navigate down (wrap around)
          menuSelected = (menuSelected + 1) % MENU_ITEM_COUNT;
          nextPiCmd = CMD_MENU_NEXT;
          Serial.print(F("Menu: selected item "));
          Serial.println(menuSelected);
          break;
        case RUNFWD:
          // Enter selected menu item - go directly to submenu ENTER command
          Serial.print(F("Menu: entering item "));
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
            case MENU_ITEM_TARGET:
              menuState = MENU_TARGET;
              targetMode = true;
              nextPiCmd = CMD_TARGET_ENTER;
              break;
            case MENU_ITEM_WIFI:
              menuState = MENU_WIFI;
              wifiMode = true;
              nextPiCmd = CMD_WIFI_ENTER;
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
              // If no specific submenu, send MENU_SELECT for Python to handle
              nextPiCmd = CMD_MENU_SELECT;
              break;
          }
          break;
        case RUNREV:
          // Exit menu
          menuState = MENU_IDLE;
          nextPiCmd = CMD_MENU_EXIT;
          Serial.println(F("Menu: exit"));
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
            Serial.println(F("Update: back to menu"));
            break;
          case REV1:
            nextPiCmd = CMD_UPDATE_PREV;
            Serial.println(F("Update: prev"));
            break;
          case FWD1:
            nextPiCmd = CMD_UPDATE_NEXT;
            Serial.println(F("Update: next"));
            break;
          case RUNFWD:
            nextPiCmd = CMD_UPDATE_CONFIRM;
            Serial.println(F("Update: confirm"));
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            updateMode = false;
            nextPiCmd = CMD_UPDATE_CANCEL;
            Serial.println(F("Update: exit menu"));
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
        Serial.println(F("Pairing mode: stop pressed"));
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
        Serial.println(F("Pairing: back to menu"));
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
            Serial.println(F("AWB: back to menu"));
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
            Serial.println(F("AWB: exit menu"));
            break;
          default:
            break;
        }
      }
    } else if (targetMode) {
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            // Go back to main menu
            menuState = MENU_MAIN;
            targetMode = false;
            nextPiCmd = CMD_TARGET_CANCEL;
            Serial.println(F("Target: back to menu"));
            break;
          case REV1:
            nextPiCmd = CMD_TARGET_PREV;
            Serial.println(F("Target: prev"));
            break;
          case FWD1:
            nextPiCmd = CMD_TARGET_NEXT;
            Serial.println(F("Target: next"));
            break;
          case RUNFWD:
            nextPiCmd = CMD_TARGET_CONFIRM;
            Serial.println(F("Target: confirm"));
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            targetMode = false;
            nextPiCmd = CMD_TARGET_CANCEL;
            Serial.println(F("Target: exit menu"));
            break;
          default:
            break;
        }
      }
    } else if (wifiMode) {
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case RUNREV:
            // Go back to main menu
            menuState = MENU_MAIN;
            wifiMode = false;
            nextPiCmd = CMD_WIFI_CANCEL;
            Serial.println(F("WiFi: back to menu"));
            break;
          case REV1:
            nextPiCmd = CMD_WIFI_PREV;
            Serial.println(F("WiFi: prev"));
            break;
          case FWD1:
            nextPiCmd = CMD_WIFI_NEXT;
            Serial.println(F("WiFi: next"));
            break;
          case RUNFWD:
            nextPiCmd = CMD_WIFI_CONFIRM;
            Serial.println(F("WiFi: confirm"));
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            wifiMode = false;
            nextPiCmd = CMD_WIFI_CANCEL;
            Serial.println(F("WiFi: exit menu"));
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
          Serial.println(F("Logs: back to menu"));
        }
      }
    } else if (menuState == MENU_UNPAIR) {
      // Note: currentButton already set at start of handleMenuSystem() - don't call pollButtons() again!
      if (currentButton != prevButton) {
        prevButton = currentButton;
        switch (currentButton) {
          case REV1:
            nextPiCmd = CMD_UNPAIR_PREV;
            Serial.println(F("Unpair: prev"));
            break;
          case FWD1:
            nextPiCmd = CMD_UNPAIR_NEXT;
            Serial.println(F("Unpair: next"));
            break;
          case RUNFWD:
            nextPiCmd = CMD_UNPAIR_CONFIRM;
            Serial.println(F("Unpair: confirm"));
            break;
          case RUNREV:
            // Go back to main menu
            menuState = MENU_MAIN;
            nextPiCmd = CMD_UNPAIR_CANCEL;
            Serial.println(F("Unpair: back to menu"));
            break;
          case STOP:
            // Exit menu completely
            menuState = MENU_IDLE;
            nextPiCmd = CMD_UNPAIR_CANCEL;
            Serial.println(F("Unpair: exit menu"));
            break;
          default:
            break;
        }
      }
    }
  }
}


void stopMotor() {
  // ...
  motorState = STOPPED;
  fwdFilmInsertedSince = 0;  // next RUNFWD run starts with fresh 30s countdown
  singleStepInProgress = false;
  Serial.println(F("Motor: Stop"));

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
  Serial.println(F("(Briefly...)"));
  delay(250);
}

void setLampMode(bool mode) {
  if (mode == lampMode)
    return;

  if (!mode)
    setZoomMode(Z1_1);

  lampMode = mode;
  Serial.print(F("Lamp mode: "));
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
  Serial.print(F("Zoom mode: "));
  Serial.print(zoomMode);
  Serial.print(F(". Telling Raspi to zoom "));
  Serial.println(zoomMode == Z1_1 ? F("out") : F("in"));
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
  fwdFilmInsertedSince = 0;
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
      Serial.println(F("AWB menu: exit"));
    }
    if ((Command)i2cCommand == CMD_TARGET_EXIT) {
      targetMode = false;
      menuState = MENU_MAIN;
      nextPiCmd = CMD_NONE;
      Serial.println(F("Target menu: exit"));
    }
    if ((Command)i2cCommand == CMD_WIFI_EXIT) {
      wifiMode = false;
      menuState = MENU_MAIN;
      nextPiCmd = CMD_NONE;
      Serial.println(F("WiFi menu: exit"));
    }
    if ((Command)i2cCommand == CMD_TARGET_REENTER) {
      targetReenterPending = true;
    }
    if ((Command)i2cCommand == CMD_MENU_EXIT) {
      // If we're in a submenu, go back to main menu; otherwise exit completely
      if (menuState != MENU_IDLE && menuState != MENU_MAIN) {
        menuState = MENU_MAIN;
        // Clear submenu modes
        updateMode = false;
        pairingMode = false;
        awbMode = false;
        targetMode = false;
        logsMode = false;
        nextPiCmd = CMD_NONE;
        Serial.println(F("Menu: back to main (from Pi)"));
      } else {
        menuState = MENU_IDLE;
        nextPiCmd = CMD_NONE;
        Serial.println(F("Menu: exit (from Pi)"));
      }
    }
    if ((Command)i2cCommand == CMD_SCAN_REJECTED) {
      if (isScanning) {
        // Reset scan state locally without sending CMD_STOP_SCAN back to Pi
        // (Pi never started scanning, so stop_scan() must not run)
        isScanning = false;
        piIsReady = false;
        setLampMode(lampModeBeforeScan);
        Serial.println(F("Scan rejected by Pi"));
      }
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
      Serial.print(F("Current Film load state: "));
      Serial.println(filmLoadState);
      Serial.print(F("Current Exposure Setting: "));
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
    Serial.println(F("Sending new Exposure Time value."));
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
  } else if (cmdToSend == CMD_UNPAIR_CANCEL && menuState == MENU_MAIN) {
    // If we just canceled unpair and menu is back to MAIN, clear the command
    // so Python can continue navigating the main menu
    nextPiCmd = CMD_NONE;
  } else {
    nextPiCmd = CMD_NONE;
  }
}
