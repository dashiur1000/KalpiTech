# שלב 1 — ASP.NET Core 8 וחיבור ל-MySQL

## מה קיים

- שרת ASP.NET Core עם יעד `net8.0`. `global.json` בוחר SDK מסדרת 8.0.4xx.
- MySQL 8.4 ב-Docker, עם מסד `VotesDb` ומשתמש יישום `kalpitech`.
- volume בשם `kalpitech_mysql_data` שומר את המסד בין הפעלות.
- חיבור המסד באמצעות MySqlConnector ושאילתת בדיקה `SELECT 1`.

`Program.cs` מרכיב את השרת ומגדיר את נתיבי HTTP. `Data/DatabaseProbe.cs`
בונה חיבור, פותח אותו ומבצע שאילתה. `await` מאפשר להמתין לפעולת המסד בלי לחסום
תהליכון, ו-`await using` משחרר את החיבור והפקודה גם כאשר מתרחשת שגיאה.
אין בשלב זה טבלאות עסקיות, טעינת CSV, התחברות או מסך משתמש.

## הרצה ב-PowerShell

לאחר מימוש שלב 3 יש להקים גם את סביבת Python; ההוראות המעודכנות נמצאות ב-[מדריך שלב 3](stage-03.md).

פתח מסוף בתיקייה הראשית של הפרויקט. Docker Desktop צריך לפעול במצב Linux containers.

אם `.env` כבר קיים מההקמה, השתמש בו. בהקמה חדשה:

```powershell
Copy-Item .env.example .env
```

ערוך את `.env` והחלף את שתי סיסמאות הדוגמה בסיסמאות שונות עם לפחות 24 אותיות
וספרות, ללא רווחים או מרכאות. הקובץ מוחרג מ-Git. אלו סיסמאות מסד הנתונים;
חשבון מנהל הבחירות יתווסף בשלב ההתחברות.

```powershell
docker compose up -d --wait
dotnet build src/KalpiTech.Api
.\scripts\run-api.ps1
```

אם מדיניות PowerShell חוסמת את הסקריפט המקומי, אפשר להריץ אותו בתהליך נפרד:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-api.ps1
```

הסקריפט קורא את סיסמת היישום ואת הפורט מתוך `.env` ומעביר אותם לשרת כמשתני
סביבה. ASP.NET Core אינו קורא קובצי `.env` מעצמו. השרת נגיש בכתובת
`http://127.0.0.1:5080`. MySQL נגיש מקומית בפורט 3307; אפשר לשנות את
`MYSQL_PORT` ב-`.env` אם הפורט תפוס ולהפעיל מחדש את המסד והשרת.

## בדיקה ידנית

השאר את השרת פועל ובמסוף שני, בתיקייה הראשית, הרץ:

```powershell
curl.exe -i http://127.0.0.1:5080/health
curl.exe -i http://127.0.0.1:5080/health/db
```

הראשון צריך להחזיר HTTP 200 ו-`{"status":"ok"}`.
השני צריך להחזיר HTTP 200 ו-`{"status":"ok","database":"VotesDb"}`.
אפשר לפתוח את שתי הכתובות גם בדפדפן.

כעת בדוק כשל בחיבור:

```powershell
docker compose stop mysql
curl.exe -i http://127.0.0.1:5080/health
curl.exe -i http://127.0.0.1:5080/health/db
```

`/health` ממשיך להחזיר 200. `/health/db` מחזיר HTTP 503 עם
`status` בערך `unavailable` והודעת "השרת אינו זמין". פרטי החריגה והסיסמה אינם
מוחזרים ללקוח. זו נקודת בדיקה תשתיתית, ולכן כשל במסד אינו אומר שתהליך ה-API נעצר.

```powershell
docker compose start --wait mysql
curl.exe -i http://127.0.0.1:5080/health/db
```

לאחר חזרת המסד, התשובה צריכה לחזור ל-200 בלי להפעיל מחדש את ה-API.

## עצירה והמשך

עצור את ה-API באמצעות Ctrl+C. עצור את MySQL באמצעות `docker compose stop`.
להפעלה חוזרת השתמש באותן פקודות הרצה. אין להשתמש ב-`docker compose down -v`
לצורך עצירה רגילה, משום שהאפשרות `-v` מוחקת את נתוני ה-volume.

משתני האתחול של MySQL יוצרים משתמשים רק כשה-volume ריק. שינוי סיסמה ב-`.env`
אחרי ההקמה אינו משנה את סיסמת המשתמש שכבר קיימת במסד.

## בדיקות שבוצעו בהקמת השלב

- SDK שנבחר: 8.0.423. בנייה הסתיימה ללא שגיאות או אזהרות.
- שחזור חבילות ובדיקת NuGet הושלמו ללא אזהרות לאחר מתן גישה לרשת.
- MySQL עלה והגיע למצב Healthy.
- כשהמסד עצור: `/health` החזיר 200 ו-`/health/db` החזיר 503 עם ההודעה המוגדרת.
- לאחר הפעלת המסד מחדש, אותו תהליך API החזיר 200 ו-`VotesDb` בבדיקת החיבור.
- `.env` מוחרג מ-Git; לא שונו נתוני ה-CSV.
- טרם נבדקו שימור רשומות עסקיות, הרשאות, CSV או הצבעות — הם אינם חלק משלב זה.

## מקורות טכניים

- [התקנת MySqlConnector](https://mysqlconnector.net/overview/installing/)
- [חיבור ל-MySQL מ-.NET](https://mysqlconnector.net/tutorials/connect-to-mysql/)
- [הגדרות MySQL ב-Docker](https://dev.mysql.com/doc/refman/8.4/en/docker-mysql-more-topics.html)
