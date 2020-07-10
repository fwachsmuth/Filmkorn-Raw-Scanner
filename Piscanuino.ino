/* 
 *  Controller for the Noris based Film Scanner
 *  
 *  Todo:
 *  - Add I2C Communication with the Raspi
 *  - FInd out why I can't program inside the board
 *  Is the USB Friend really borked?
 *  
 *  - Draw Schematics already
 *  
 *    
 *  Ideas: 
 *  - Put Trimpot(s) on open A2/A3 to allow setting base speeds
 *  
 */



// Define the Control Buttons
#define NONE  0 // No Button pressed
#define ZOOM  1 // Toggle 
#define LIGHT 2 // Toggle 
#define REV   3 // Radio 
#define REV1  4 // Push 
#define STOP  5 // Radio 
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
#define TRIGGER_PIN     7
#define EYE_PIN         2   // ISR
#define BUTTONS_A_PIN   A0
#define BUTTONS_B_PIN   A1

// Define some constants
const uint8_t  singleFrameMotorPower = 170; // 255 would be full power
const uint8_t  fps18MotorPower = 200;
const uint8_t  fps24MotorPower = 220;

// Define some global variables
uint8_t myState = STATE_IDLE;
uint8_t prevState = STATE_IDLE;
uint8_t currentButton;
uint8_t prevButtonChoice;
int8_t  motorState = MOTOR_STOPPED;
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
  pinMode(EYE_PIN, INPUT);

//  attachInterrupt(digitalPinToInterrupt(EYE_PIN), motorStopISR, RISING);

  // Stop the engines
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, 0);
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
            setLampMode(false);
            isScanning = false;
            Serial.println("Scanning mode: 0");
            // ...
          } else {
            stopMotor();
          }
        break;
        case REV:
          if (motorState == MOTOR_FWD)
            stopBriefly();
          motorState = MOTOR_REV;
          Serial.println("Motor: <<");
          motorRev();
        break;
        case REV1:
          if (motorState != MOTOR_STOPPED)
            break;
          Serial.println("<");
          motorREV1();
        break;
        case FWD1:
          if (motorState != MOTOR_STOPPED)
            break;
          Serial.println(">");
          motorFWD1();
        break;
        case FWD:
          if (motorState == MOTOR_REV)
            stopBriefly();
          motorState = MOTOR_FWD;
          Serial.println("Motor: >>");
          motorFwd();
        break;
        case SCAN:
          if (motorState != MOTOR_STOPPED)
            stopBriefly();
          setZoomMode(false);
          setLampMode(true);
          isScanning = true;
          Serial.println("Scanning mode: 1");
          // ...
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
  
  /* 
  Enable the below three lines if breaking makes sense
  */
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
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, RISING);
  analogWrite(MOTOR_A_PIN, singleFrameMotorPower);
  analogWrite(MOTOR_B_PIN, 0);
  
}

void motorREV1() {
  attachInterrupt(digitalPinToInterrupt(EYE_PIN), stopMotorISR, RISING);
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, singleFrameMotorPower);
}

void motorFwd() {
  analogWrite(MOTOR_A_PIN, fps18MotorPower);
  analogWrite(MOTOR_B_PIN, 0);
}

void motorRev() {
  analogWrite(MOTOR_A_PIN, 0);
  analogWrite(MOTOR_B_PIN, fps18MotorPower);
}

void stopMotorISR() {
  detachInterrupt(digitalPinToInterrupt(EYE_PIN));
  stopMotor();
}

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
      buttonChoice = REV;
    } else if (buttonBankA > 990)                      {
      buttonChoice = REV1;
    }
    
    if (buttonBankB > 30 && buttonBankB < 70)          {
      buttonChoice = STOP;
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
