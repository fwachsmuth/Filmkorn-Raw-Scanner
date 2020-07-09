// Define the Control Buttons
#define NONE  0 // No Button pressed
#define ZOOM  1 // Toggle 
#define LIGHT 2 // Toggle 
#define STOP  3 // Radio 
#define REV   4 // Radio 
#define REV1  5 // Push 
#define FWD1  6 // Push 
#define FWD   7 // Radio 
#define SCAN  8 // Radio 

// Define the States we can be in
#define STATE_IDLE    1
#define STATE_SCAN    2
#define STATE_PREVIEW 3
#define STATE_RUN     4

// Define the motor states
#define MOTOR_REV -1
#define MOTOR_STOPPED    0
#define MOTOR_FWD   1

// Define the Hardware wiring
#define FAN_PIN         8
#define LAMP_PIN        9
#define MOTOR_A_PIN     6   // PWM
#define MOTOR_B_PIN     5   // PWM
#define TRIGGER_PIN    10
#define RELAIS_PIN      7
#define EYE_PIN         2   // ISR

#define BUTTONS_A_PIN   A0
#define BUTTONS_B_PIN   A1


// Define some global variables
uint8_t myState = STATE_IDLE;
uint8_t prevState = STATE_IDLE;
uint8_t currentButton;
uint8_t prevButtonChoice;
int8_t motorState = MOTOR_STOPPED;
bool    lampMode = false;
bool    zoomMode = false;
bool    isScanning = false;
uint8_t speed = 0;

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  pinMode(BUTTONS_A_PIN, INPUT);
  pinMode(BUTTONS_B_PIN, INPUT);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(LAMP_PIN, OUTPUT);
  pinMode(MOTOR_A_PIN, OUTPUT);
  pinMode(MOTOR_B_PIN, OUTPUT);
  pinMode(TRIGGER_PIN, OUTPUT);
  pinMode(RELAIS_PIN, OUTPUT);
  pinMode(EYE_PIN, INPUT);

//  attachInterrupt(digitalPinToInterrupt(EYE_PIN), motorStopISR, RISING);

  
  // Temp Motor Testing
  analogWrite(MOTOR_A_PIN, 0);
  digitalWrite(MOTOR_B_PIN, LOW);
}

void loop() {
  currentButton = pollButtons();

  if (currentButton != prevButtonChoice) {
    prevButtonChoice = currentButton;

    if (!isScanning || currentButton == STOP)
      switch (currentButton) {
        case NONE:
        break;
        case ZOOM:
          setZoomMode(!zoomMode);
        break;
        case LIGHT:
          setLampMode(!lampMode);
        break;
        case STOP:
          if (isScanning) {
            // ...
            setLampMode(false);
            isScanning = false;
            Serial.println("Scanning mode: 0");
          } else {
            stopMotor();
          }
        break;
        case REV:
          if (motorState == MOTOR_FWD)
            stopBriefly();
          // ...
          motorState = MOTOR_REV;
          Serial.println("Motor: <<");
        break;
        case REV1:
          if (motorState != MOTOR_STOPPED)
            break;
          // ...
          Serial.println("<");
        break;
        case FWD1:
          if (motorState != MOTOR_STOPPED)
            break;
          // ...
          Serial.println(">");
        break;
        case FWD:
          if (motorState == MOTOR_REV)
            stopBriefly();
          // ...
          motorState = MOTOR_FWD;
          Serial.println("Motor: >>");
        break;
        case SCAN:
          if (motorState != MOTOR_STOPPED)
            stopBriefly();
          setZoomMode(false);
          setLampMode(true);
          isScanning = true;
          Serial.println("Scanning mode: 1");
        break;
        default:
        break;
      }
  }
  
}

void stopMotor() {
  // ...
  motorState = MOTOR_STOPPED;
  Serial.println("Motor: Stop");
}

void stopBriefly() {
  stopMotor();
  delay(1000);
}

void setLampMode(bool mode) {
  if (mode == lampMode)
    return;
  if (!mode && zoomMode)
    setZoomMode(false);
  // ...
  lampMode = mode;
  Serial.print("Lamp mode: ");
  Serial.println(lampMode);
}

void setZoomMode(bool mode) {
  if (mode == zoomMode)
    return;
  if (mode && !lampMode)
    setLampMode(true);
  // ...
  zoomMode = mode;
  Serial.print("Zoom mode: ");
  Serial.println(zoomMode);
}

/* 
void motorFWD1() {
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), motorStopISR, RISING);
  analogWrite(MOTOR_A_PIN, 200);
  analogWrite(MOTOR_B_PIN, 200);
  digitalWrite(MOTOR_A_PIN, HIGH);
  digitalWrite(MOTOR_B_PIN, LOW);
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
}

void motorStopISR() {
  digitalWrite(MOTOR_A_PIN, LOW);
  digitalWrite(MOTOR_B_PIN, LOW);
}
*/

int pollButtons() {
  int buttonBankA;
  int buttonBankB;
  static bool noButtonPressed;
  int buttonChoice;
  
  buttonBankA = analogRead(A0);
  buttonBankB = analogRead(A1);

  if (noButtonPressed == true) {    
    if (buttonBankA < 2 && buttonBankB < 2) {
      buttonChoice = NONE;
    } else if (buttonBankA > 30 && buttonBankA < 70)          {
      buttonChoice = ZOOM;
    } else if (buttonBankA > 120 && buttonBankA < 160) {
      buttonChoice = LIGHT;
    } else if (buttonBankA > 290 && buttonBankA < 330) {
      buttonChoice = STOP;
    } else if (buttonBankA > 990)                      {
      buttonChoice = REV;
    }
    
    if (buttonBankB > 30 && buttonBankB < 70)          {
      buttonChoice = REV1;
    } else if (buttonBankB > 120 && buttonBankB < 160) {
      buttonChoice = FWD1;
    } else if (buttonBankB > 290 && buttonBankB < 330) {
      buttonChoice = FWD;
    } else if (buttonBankB > 990)                      {
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
