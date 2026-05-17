#pragma once
#include <Arduino.h>

// ============================================================
// Sunrise / sunset lookup table – Budapest, Hungary
// Latitude: 47.5°N   Longitude: 19.1°E
// Timezone: CET (UTC+1) winter, CEST (UTC+2) summer
//
// Times are LOCAL clock minutes from midnight (0–1439).
// DST already incorporated:
//   Weeks  1–12 : CET  (UTC+1)
//   Weeks 13–43 : CEST (UTC+2)   (transition ~last Sunday of March)
//   Weeks 44–52 : CET  (UTC+1)   (transition ~last Sunday of October)
//
// Accuracy: ±15 min – sufficient for sleep scheduling.
// Index 0 = ISO week 1, index 51 = ISO week 52.
// ============================================================

static const uint32_t NIGHT_SLEEP_MAX_SEC = 12UL * 3600UL; // 12-hour safety cap
static const uint16_t SUNRISE_BUFFER_MIN  = 15U;           // wake 15 min before sunrise
static const int16_t NIGHT_SLEEP_START_OFFSET_MIN = -60;   // start night sleep 60 min earlier
static const int16_t NIGHT_WAKE_OFFSET_MIN = 30;           // wake 30 min later

struct SunTimes {
    uint16_t sunrise; // minutes from midnight, local time
    uint16_t sunset;  // minutes from midnight, local time
};

static const SunTimes SUN_TABLE[52] = {
  // sunrise  sunset    week  date       local times (CET unless noted)
    {453,  957},  // W01  Jan  1   07:33 – 15:57
    {452,  965},  // W02  Jan  8   07:32 – 16:05
    {448,  975},  // W03  Jan 15   07:28 – 16:15
    {441,  987},  // W04  Jan 22   07:21 – 16:27
    {432,  999},  // W05  Jan 29   07:12 – 16:39
    {421, 1012},  // W06  Feb  5   07:01 – 16:52
    {408, 1026},  // W07  Feb 12   06:48 – 17:06
    {393, 1040},  // W08  Feb 19   06:33 – 17:20
    {377, 1053},  // W09  Feb 26   06:17 – 17:33
    {361, 1067},  // W10  Mar  5   06:01 – 17:47
    {343, 1080},  // W11  Mar 12   05:43 – 18:00
    {325, 1094},  // W12  Mar 19   05:25 – 18:14
    {367, 1167},  // W13  Mar 26   06:07 – 19:27  [CEST begins ~Mar 29]
    {350, 1180},  // W14  Apr  2   05:50 – 19:40
    {333, 1193},  // W15  Apr  9   05:33 – 19:53
    {317, 1206},  // W16  Apr 16   05:17 – 20:06
    {302, 1219},  // W17  Apr 23   05:02 – 20:19
    {289, 1231},  // W18  Apr 30   04:49 – 20:31
    {277, 1244},  // W19  May  7   04:37 – 20:44
    {267, 1256},  // W20  May 14   04:27 – 20:56
    {259, 1267},  // W21  May 21   04:19 – 21:07
    {253, 1276},  // W22  May 28   04:13 – 21:16
    {249, 1285},  // W23  Jun  4   04:09 – 21:25
    {247, 1291},  // W24  Jun 11   04:07 – 21:31
    {247, 1295},  // W25  Jun 18   04:07 – 21:35
    {250, 1295},  // W26  Jun 25   04:10 – 21:35
    {255, 1292},  // W27  Jul  2   04:15 – 21:32
    {262, 1285},  // W28  Jul  9   04:22 – 21:25
    {271, 1276},  // W29  Jul 16   04:31 – 21:16
    {281, 1265},  // W30  Jul 23   04:41 – 21:05
    {292, 1251},  // W31  Jul 30   04:52 – 20:51
    {304, 1236},  // W32  Aug  6   05:04 – 20:36
    {316, 1219},  // W33  Aug 13   05:16 – 20:19
    {328, 1201},  // W34  Aug 20   05:28 – 20:01
    {340, 1182},  // W35  Aug 27   05:40 – 19:42
    {352, 1163},  // W36  Sep  3   05:52 – 19:23
    {364, 1142},  // W37  Sep 10   06:04 – 19:02
    {376, 1122},  // W38  Sep 17   06:16 – 18:42
    {388, 1101},  // W39  Sep 24   06:28 – 18:21
    {400, 1080},  // W40  Oct  1   06:40 – 18:00
    {412, 1060},  // W41  Oct  8   06:52 – 17:40
    {424, 1041},  // W42  Oct 15   07:04 – 17:21
    {437, 1022},  // W43  Oct 22   07:17 – 17:02
    {390, 1004},  // W44  Oct 29   06:30 – 16:44  [CET begins ~Oct 25]
    {404,  988},  // W45  Nov  5   06:44 – 16:28
    {418,  974},  // W46  Nov 12   06:58 – 16:14
    {432,  962},  // W47  Nov 19   07:12 – 16:02
    {444,  952},  // W48  Nov 26   07:24 – 15:52
    {454,  946},  // W49  Dec  3   07:34 – 15:46
    {461,  944},  // W50  Dec 10   07:41 – 15:44
    {465,  945},  // W51  Dec 17   07:45 – 15:45
    {464,  950},  // W52  Dec 24   07:44 – 15:50
};

// ---------------------------------------------------------------
// Returns seconds to sleep until (sunrise - SUNRISE_BUFFER_MIN + NIGHT_WAKE_OFFSET_MIN).
// Returns 0 if it is currently daytime – no night sleep needed.
// Caps at NIGHT_SLEEP_MAX_SEC (12 h) as a safety fallback.
// ---------------------------------------------------------------
inline uint32_t secondsUntilSunrise(int isoWeek, int currentMinutes) {
    if (isoWeek < 1)  isoWeek = 1;
    if (isoWeek > 52) isoWeek = 52;

    const SunTimes& st = SUN_TABLE[isoWeek - 1];

    int wakeMin = static_cast<int>(st.sunrise) - static_cast<int>(SUNRISE_BUFFER_MIN) + static_cast<int>(NIGHT_WAKE_OFFSET_MIN);
    if (wakeMin < 0) wakeMin = 0;
    if (wakeMin > 1439) wakeMin = 1439;

    int sleepMin = static_cast<int>(st.sunset) + static_cast<int>(NIGHT_SLEEP_START_OFFSET_MIN);
    if (sleepMin < 0) sleepMin = 0;
    if (sleepMin > 1439) sleepMin = 1439;

    // Daytime: between adjusted sunrise and sunset
    if (currentMinutes >= wakeMin && currentMinutes < sleepMin) {
        return 0; // no sleep needed
    }

    // Night: minutes until sunrise (possibly tomorrow)
    int minsToSunrise;
    if (currentMinutes < wakeMin) {
        // Before sunrise today
        minsToSunrise = wakeMin - currentMinutes;
    } else {
        // After sunset – sunrise is tomorrow
        minsToSunrise = (1440 - currentMinutes) + wakeMin;
    }

    uint32_t secs = static_cast<uint32_t>(minsToSunrise) * 60UL;
    if (secs > NIGHT_SLEEP_MAX_SEC) secs = NIGHT_SLEEP_MAX_SEC;
    return secs;
}
