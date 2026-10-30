// PhaseBreathe ESP32 + HC-SR04; serial format DIST,<cm>
#define TRIG_PIN 5
#define ECHO_PIN 18 // ECHO MUST pass through voltage divider
const unsigned long TIMEOUT_US=15000;      // 250 cm round trip is ~14.6 ms
const unsigned long SAMPLE_PERIOD_MS=40;   // 25 Hz; raise toward 60 if you see ghost echoes from far walls
void setup(){ Serial.begin(115200); pinMode(TRIG_PIN,OUTPUT); pinMode(ECHO_PIN,INPUT); digitalWrite(TRIG_PIN,LOW); delay(500); Serial.println("PHASEBREATHE_READY"); }
void loop(){
 unsigned long start=millis();
 digitalWrite(TRIG_PIN,LOW); delayMicroseconds(3);
 digitalWrite(TRIG_PIN,HIGH); delayMicroseconds(10); digitalWrite(TRIG_PIN,LOW);
 unsigned long duration=pulseIn(ECHO_PIN,HIGH,TIMEOUT_US);
 if(duration){ float cm=duration*0.0343f/2.0f; if(cm>2 && cm<250){Serial.print("DIST,");Serial.println(cm,2);}else Serial.println("INVALID");}
 else Serial.println("INVALID");
 // fixed period: measurement time no longer adds to the delay
 unsigned long spent=millis()-start;
 if(spent<SAMPLE_PERIOD_MS) delay(SAMPLE_PERIOD_MS-spent);
}
