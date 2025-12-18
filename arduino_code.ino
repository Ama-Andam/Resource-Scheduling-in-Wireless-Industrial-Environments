#include <WiFi.h>

/************************************************************
 *  WIFI CONFIG
 ************************************************************/
const char* WIFI_SSID     = "cd2090";
const char* WIFI_PASSWORD = "251201030597";

// PC (Python) TCP server:
const char* SERVER_IP   = "192.168.0.120";   
const uint16_t SERVER_PORT = 5000;

WiFiClient client;

/************************************************************
 *  PINS  (ESP32-WROOM-32D, 38-pin)
 ************************************************************/
#define PIR_PIN       19
#define BUTTON_PIN    23
#define TRIG_PIN      18
#define ECHO_PIN       5
#define SOUND_PIN     34    // ADC1 channel

/************************************************************
 *  TASK / EDF CONFIG
 ************************************************************/
struct Task {
  const char* name;
  uint32_t period;        // ms (0 for purely event-driven)
  uint32_t rel;           // release time r
  uint32_t dl;            // absolute deadline d
  bool     ready;         // is job ready?
  uint32_t nextRelease;   // for periodic tasks
  uint32_t jobId;         // job counter
};

uint32_t now_ms() { return millis(); }

// Periods / deadlines (you can tune):
// ULTRA: High-frequency safety-critical sensor (collision avoidance)
const uint32_t ULTRA_PERIOD  = 200;   // 200 ms - HIGH PRIORITY
const uint32_t ULTRA_DEADLINE = 180;  // 180 ms - tight deadline (90% of period)

// SOUND: Lower-frequency monitoring sensor (machine health)
const uint32_t SOUND_PERIOD  = 2000;  // 2 s - LOW PRIORITY
const uint32_t SOUND_DEADLINE = 1950; // 1950 ms - relaxed deadline (97.5% of period)

// Global tasks
Task t_ultra  = {"Ultra",  ULTRA_PERIOD, 0, 0, false, 0, 0};
Task t_sound  = {"Sound",  SOUND_PERIOD, 0, 0, false, 0, 0};
Task t_pir    = {"PIR",             0, 0, 0, false, 0, 0};
Task t_button = {"Button",          0, 0, 0, false, 0, 0};

/************************************************************
 *  UTIL
 ************************************************************/
void sendLine(const String& s) {
  if (!client.connected()) return;
  client.print(s);
  client.print('\n');
}

uint16_t readUltra() {
  // Ultrasonic distance sensor - fast, safety-critical
  // Execution time: ~10-30ms depending on distance
  // Deadline: 180ms (high-priority, must complete frequently)
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long dur = pulseIn(ECHO_PIN, HIGH, 30000);  // timeout 30 ms
  if (dur <= 0) return 0;
  return dur / 58;   // cm
}

uint16_t readSound() {
  // Optimized "RMS-ish" average with reduced blocking time
  // Original: 50 samples × 2ms = 100ms total (blocking!)
  // Optimized: 12 samples × 200µs = 2.4ms total (41x faster!)
  const int N = 12;
  uint32_t sum = 0;
  for (int i = 0; i < N; i++) {
    sum += analogRead(SOUND_PIN);
    delayMicroseconds(200);  // 200 microseconds instead of 2ms
  }
  return sum / N;
}

/************************************************************
 *  EDF PICKER
 ************************************************************/
Task* pickEDF() {
  Task* best = nullptr;
  uint32_t bestDL = 0xFFFFFFFF;

  Task* all[] = { &t_ultra, &t_sound, &t_pir, &t_button };
  for (Task* t : all) {
    if (t->ready) {
      if (t->dl < bestDL) {
        bestDL = t->dl;
        best   = t;
      }
    }
  }
  return best;
}

/************************************************************
 *  SETUP
 ************************************************************/
void setup() {
  Serial.begin(115200);

  pinMode(PIR_PIN,    INPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(TRIG_PIN,   OUTPUT);
  pinMode(ECHO_PIN,   INPUT);
  pinMode(SOUND_PIN,  INPUT);

  // WiFi connect
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected, IP = " + WiFi.localIP().toString());

  // Connect TCP to PC
  while (!client.connect(SERVER_IP, SERVER_PORT)) {
    Serial.println("Connecting to server...");
    delay(1000);
  }
  Serial.println("Connected to server.");
  
  // Print task configuration
  Serial.println("\n=== EDF SCHEDULER CONFIGURATION ===");
  Serial.println("ULTRA: period=200ms, deadline=180ms (safety-critical, high-priority)");
  Serial.println("SOUND: period=2000ms, deadline=1950ms (monitoring, low-priority)");
  Serial.println("PIR & Button: event-driven (motion/emergency)");
  Serial.println("===================================\n");

  uint32_t t = now_ms();
  t_ultra.nextRelease = t;
  t_sound.nextRelease = t;
}

/************************************************************
 *  MAIN LOOP
 ************************************************************/
void loop() {
  uint32_t now = now_ms();

  // 1) Periodic releases
  if (!t_ultra.ready && now >= t_ultra.nextRelease) {
    t_ultra.rel = t_ultra.nextRelease;
    t_ultra.dl  = t_ultra.rel + ULTRA_DEADLINE;
    t_ultra.ready = true;
    t_ultra.jobId++;
  }

  if (!t_sound.ready && now >= t_sound.nextRelease) {
    t_sound.rel = t_sound.nextRelease;
    t_sound.dl  = t_sound.rel + SOUND_DEADLINE;
    t_sound.ready = true;
    t_sound.jobId++;
  }

  // 2) Event releases (PIR & Button)
  if (digitalRead(PIR_PIN) == HIGH && !t_pir.ready) {
    t_pir.rel    = now;
    t_pir.dl     = now + 50;   // short deadline
    t_pir.ready  = true;
    t_pir.jobId++;
  }

  if (digitalRead(BUTTON_PIN) == LOW && !t_button.ready) {
    t_button.rel    = now;
    t_button.dl     = now + 50; // short deadline
    t_button.ready  = true;
    t_button.jobId++;
  }

  // 3) EDF select
  Task* t = pickEDF();
  if (!t) {
    // nothing ready; small idle delay
    delay(1);
    return;
  }

  uint32_t start = now_ms();

  // Log EDF start
  String edfMsg = "EDF name=" + String(t->name) +
                  " job=" + String(t->jobId) +
                  " rel=" + String(t->rel) +
                  " start=" + String(start) +
                  " dl=" + String(t->dl);
  sendLine(edfMsg);

  // 4) Run task
  uint16_t val = 0;
  if (t == &t_ultra) {
    val = readUltra();
    t_ultra.nextRelease = t_ultra.rel + ULTRA_PERIOD;
  } else if (t == &t_sound) {
    val = readSound();
    t_sound.nextRelease = t_sound.rel + SOUND_PERIOD;
  } else if (t == &t_pir) {
    val = 1;      // event
  } else if (t == &t_button) {
    val = 1;
  }

  uint32_t end = now_ms();

  // task completed
  t->ready = false;

  // Log DONE
  String doneMsg = "DONE name=" + String(t->name) +
                   " job=" + String(t->jobId) +
                   " end=" + String(end) +
                   " val=" + String(val);
  sendLine(doneMsg);
}