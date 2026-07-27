/*
 * REFERENS SKICH: ESP32 da on-device FFT.
 *
 * Nima qiladi:
 *   - Akselerometrdan SAMPLING_FREQUENCY chastotada SAMPLES ta o'lchov oladi
 *   - Har oynada bitta DATA qatori (o'rtacha |x|,|y|,|z|) chiqaradi
 *   - Har SPEC_EVERY oynada FFT hisoblab SPEC qatori chiqaradi
 *
 * Serial protokol (collector.py shu formatni kutadi):
 *   DATA:x,y,z
 *   SPEC:<fs>:<a0,a1,...,aN>   // i-bin chastotasi = i*fs/(2*N_bins)
 *   N_bins = SAMPLES/2 — collector'dagi SPEC_BINS bilan bir xil bo'lsin!
 *
 * MUHIM (FFT sifatiga ta'sir qiladi):
 *   - FFT ga ISHORALI kompozit beriladi va oyna O'RTACHASI AYIRILADI —
 *     aks holda gravitatsiya (DC) past chastota diapazoniga "oqib",
 *     tashxis doim "balanssizlik" bo'lib qoladi.
 *   - SPEC qatoriga nominal emas, O'LCHANGAN real chastota yoziladi:
 *     sekin sensor o'qishda (masalan I2C 100 kHz) real chastota pasayadi,
 *     nominalni yozish butun chastota o'qini siljitib yuborardi.
 *   - MPU6050/I2C ishlatsangiz: Wire.setClock(400000); qiling, aks holda
 *     100 kHz da 2048 Hz ga ulgurmaydi.
 *
 * Kutubxona: "arduinoFFT" (Library Manager dan, v2.x).
 * !!! readAccel() ni O'Z SENSORINGIZGA moslang (pastda MPU6050 misoli).
 */

 #include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "MUV-1";       // Zavodagi Wi-Fi nomi
const char* password = "MUV2025!2026";  // Wi-Fi paroli
const char* serverUrl = "http://SERVER_IP_MANZILI:8000/api/vibration"; // main.py ishlayotgan kompyuter yoki server IP-si
const char* spectrumUrl = "http://SERVER_IP_MANZILI:8000/api/spectrum";
const char* apiKey = "API_KEY";      // main.py dagi API_KEY bilan bir xil bo'lishi kerak
const char* bearingName = "Bearing 4";         // Ushbu sensor o'rnatilganuskuna/podshivnik nomi


#include <arduinoFFT.h>

#define SAMPLES            256           // FFT o'lchami (2 ning darajasi)
#define SAMPLING_FREQUENCY 2048          // Hz — 300+ Hz diagnostika uchun yetarli
#define SPEC_EVERY         5             // har nechta oynada bitta SPEC yuborish

double vReal[SAMPLES];
double vImag[SAMPLES];
ArduinoFFT<double> FFT(vReal, vImag, SAMPLES, SAMPLING_FREQUENCY);

unsigned long samplePeriodUs;
int windowCounter = 0;

// ---- SENSORGA MOSLANG ----------------------------------------------------
// MPU6050 uchun (Wire + MPU6050 kutubxonasi bilan) taxminan:
//   setup() da: Wire.begin(); Wire.setClock(400000); mpu.initialize();
//   bu yerda:   mpu.getAcceleration(&ax, &ay, &az);
//               x = ax / 16384.0; y = ay / 16384.0; z = az / 16384.0; // g
void readAccel(double &x, double &y, double &z) {
  x = analogRead(34) / 4095.0;  // STUB — almashtiring!
  y = analogRead(35) / 4095.0;
  z = analogRead(36) / 4095.0;
}
// ---------------------------------------------------------------------------

// void setup() {
//   Serial.begin(115200);
//   samplePeriodUs = round(1000000.0 / SAMPLING_FREQUENCY);
// }

void setup() {
  Serial.begin(115200);
  samplePeriodUs = round(1000000.0 / SAMPLING_FREQUENCY);

  // Wi-Fi ga ulanishni qo'shamiz
  WiFi.begin(ssid, password);
  Serial.print("Wi-Fi ga ulanmoqda");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWi-Fi ulandi!");
  Serial.print("IP manzil: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  double sumX = 0, sumY = 0, sumZ = 0;
  double mean = 0;
  unsigned long windowStartUs = micros();

  // Bitta oyna: SAMPLES ta o'lchov, qat'iy chastotada
  for (int i = 0; i < SAMPLES; i++) {
    unsigned long t0 = micros();
    double x, y, z;
    readAccel(x, y, z);
    sumX += fabs(x); sumY += fabs(y); sumZ += fabs(z);
    // FFT uchun ISHORALI kompozit (fabs YO'Q — to'g'rilash chastotani
    // ikki baravar oshirib ko'rsatadi)
    vReal[i] = (x + y + z) / 3.0;
    mean += vReal[i];
    vImag[i] = 0;
    while (micros() - t0 < samplePeriodUs) { /* keyingi o'lchovni kutish */ }
  }
  double windowSeconds = (micros() - windowStartUs) / 1000000.0;
  double realFs = SAMPLES / windowSeconds;  // real (o'lchangan) chastota

  // DC/gravitatsiyani olib tashlash: oyna o'rtachasini ayirish
  mean /= SAMPLES;
  for (int i = 0; i < SAMPLES; i++) vReal[i] -= mean;

  // DATA: oynaning o'rtacha |a| qiymatlari
  Serial.print("DATA:");
  Serial.print(sumX / SAMPLES, 4); Serial.print(",");
  Serial.print(sumY / SAMPLES, 4); Serial.print(",");
  Serial.println(sumZ / SAMPLES, 4);

  // SPEC: har SPEC_EVERY oynada, real o'lchangan chastota bilan
  if (++windowCounter >= SPEC_EVERY) {
    windowCounter = 0;
    FFT.windowing(FFTWindow::Hamming, FFTDirection::Forward);
    FFT.compute(FFTDirection::Forward);
    FFT.complexToMagnitude();  // vReal[0..SAMPLES/2] — amplitudalar

    Serial.print("SPEC:");
    Serial.print(realFs, 1);
    Serial.print(":");
    for (int i = 0; i < SAMPLES / 2; i++) {
      if (i) Serial.print(",");
      Serial.print(vReal[i], 4);
    }
    Serial.println();
  }
}
