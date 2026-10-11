using KalpiTech.Api.Models;
using KalpiTech.Api.Services;

var start = new DateTime(2026, 10, 11, 6, 0, 0, DateTimeKind.Utc);
var end = start.AddHours(12);
var schedule = new ElectionSchedule(start, end);
var count = 0;
void Check(bool condition) { count++; if (!condition) throw new Exception($"Check {count} failed"); }
Check(new ElectionSchedule(null, null).State(start) == "Preparation");
Check(schedule.State(start.AddTicks(-1)) == "Preparation");
Check(schedule.State(start) == "Active");
Check(schedule.State(end.AddTicks(-1)) == "Active");
Check(schedule.State(end) == "Finished");
Check(!schedule.InCommitteeWindow(start.AddTicks(-1)));
Check(schedule.InCommitteeWindow(start));
Check(schedule.InCommitteeWindow(end));
Check(schedule.InCommitteeWindow(start.AddHours(36).AddTicks(-1)));
Check(!schedule.InCommitteeWindow(start.AddHours(36)));
Check(!schedule.HasStarted(start.AddTicks(-1)) && schedule.HasStarted(start));
Check(IsraelTime.TryParse("2026-01-15T12:00", out var winter) && winter.Hour == 10);
Check(IsraelTime.TryParse("2026-07-15T12:00", out var summer) && summer.Hour == 9);
Check(IsraelTime.Format(winter) == "2026-01-15T12:00");
Check(!IsraelTime.TryParse("2026-03-27T02:30", out _));
Check(!IsraelTime.TryParse("2026-10-25T01:30", out _));
Check(!IsraelTime.TryParse("2026-01-15T12:00Z", out _));
Console.WriteLine($"Passed {count} election boundary and Israel-time checks.");
