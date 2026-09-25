// SPDX-License-Identifier: BSD-2-Clause-Patent
// Native single-file companion to the existing WPF GUI. No firmware/driver writes.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <windowsx.h>
#include <winioctl.h>
#include <commctrl.h>
#include <shellapi.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <gdiplus.h>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include "../../Rpi5Fan/Rpi5FanIoctl.h"
#include "Animation.h"

using namespace Gdiplus;
using Clock = std::chrono::steady_clock;
static_assert(sizeof(RPI5FAN_STATUS) == 64, "Driver API layout changed");
static_assert(sizeof(RPI5FAN_MANUAL_REQUEST) == 8, "Request layout changed");
static_assert(IOCTL_RPI5FAN_GET_STATUS == 0x83376000u, "IOCTL changed");
static_assert(IOCTL_RPI5FAN_SET_MANUAL == 0x8337a008u, "IOCTL changed");
constexpr UINT WM_SAMPLE = WM_APP + 1;
constexpr int AUTO = 201, MANUAL = 202, FULL = 203, PAUSE = 204,
              LOGS = 205, SLIDER = 206, LOGVIEW = 207;
const Color Background(255, 15, 23, 36), Card(255, 23, 33, 49),
    Edge(255, 40, 57, 78), Text(255, 237, 244, 255), Muted(255, 148, 166, 190),
    Accent(255, 93, 228, 199), Warning(255, 255, 194, 117), Danger(255, 255, 131, 150);
struct Failure { std::wstring message; };
std::wstring ErrorText(DWORD code) {
    wchar_t* p = nullptr;
    FormatMessageW(FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
                   FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, code, 0,
                   reinterpret_cast<wchar_t*>(&p), 0, nullptr);
    std::wstring s = p ? p : L"Unknown Windows error";
    if (p) LocalFree(p);
    while (!s.empty() && (s.back() == L'\r' || s.back() == L'\n')) s.pop_back();
    return s + L" (" + std::to_wstring(code) + L")";
}
class Device {
    HANDLE h_ = INVALID_HANDLE_VALUE;
public:
    ~Device() { Close(); }
    void Close() { if (h_ != INVALID_HANDLE_VALUE) CloseHandle(h_); h_ = INVALID_HANDLE_VALUE; }
    void Open() {
        if (h_ != INVALID_HANDLE_VALUE) return;
        h_ = CreateFileW(L"\\\\.\\Rpi5Fan", GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, 0, nullptr);
        if (h_ == INVALID_HANDLE_VALUE) throw Failure{L"Fan driver unavailable: " + ErrorText(GetLastError())};
    }
    void Ioctl(DWORD code, void* in, DWORD inSize, void* out, DWORD outSize, DWORD& returned) {
        Open();
        if (!DeviceIoControl(h_, code, in, inSize, out, outSize, &returned, nullptr)) {
            DWORD e = GetLastError(); Close();
            throw Failure{L"Fan driver request failed: " + ErrorText(e)};
        }
    }
    RPI5FAN_STATUS Read() {
        RPI5FAN_STATUS s{}; DWORD got = 0;
        Ioctl(IOCTL_RPI5FAN_GET_STATUS, nullptr, 0, &s, sizeof(s), got);
        if (got < sizeof(s) || s.Size < sizeof(s) || s.ApiVersion != RPI5FAN_API_VERSION)
            throw Failure{L"Incompatible driver. This GUI needs the exp.6 API v2 fan driver."};
        if (s.CurrentPercent > 100 || s.RequestedPercent > 100 || s.ControlMode > 1)
            throw Failure{L"Invalid fan status record; controls have been disabled."};
        return s;
    }
    void Command(int command, unsigned percent) {
        // Validate the live protocol before every write, not just at launch.
        auto s = Read();
        if (!s.HardwareReady) throw Failure{L"Fan hardware is not ready; request not sent."};
        DWORD got = 0;
        if (command == MANUAL) {
            if (percent < 30 || percent > 100) throw Failure{L"Manual speed must be 30-100%."};
            RPI5FAN_MANUAL_REQUEST r{sizeof(r), percent};
            Ioctl(IOCTL_RPI5FAN_SET_MANUAL, &r, sizeof(r), nullptr, 0, got);
        } else if (command == AUTO || command == FULL) {
            Ioctl(command == AUTO ? IOCTL_RPI5FAN_SET_AUTO : IOCTL_RPI5FAN_SET_FAILSAFE,
                  nullptr, 0, nullptr, 0, got);
        }
    }
};
struct Sample {
    bool connected = false;
    RPI5FAN_STATUS status{};
    std::wstring error, event, logWarning;
};
std::wstring LogDirectory() {
    PWSTR p = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_LocalAppData, 0, nullptr, &p))) return {};
    std::wstring dir = std::wstring(p) + L"\\Rpi5Fan\\Logs"; CoTaskMemFree(p);
    std::error_code ec; std::filesystem::create_directories(dir, ec);
    return ec ? std::wstring() : dir;
}
std::string Utf8(const std::wstring& s) {
    if (s.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), nullptr, 0, nullptr, nullptr);
    std::string r(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), r.data(), n, nullptr, nullptr);
    return r;
}
std::string Csv(const std::wstring& s) {
    std::string r = "\"";
    for (char c : Utf8(s)) { if (c == '"') r += '"'; r += (c == '\r' || c == '\n') ? ' ' : c; }
    return r + "\"";
}
void LogSample(Sample& sample, const std::wstring& dir) noexcept {
    // Disk/log failures must never turn a healthy driver into an unavailable driver.
    try {
        if (dir.empty()) { sample.logWarning = L"Logging unavailable: cannot create the log directory."; return; }
        SYSTEMTIME t{}; GetLocalTime(&t);
        wchar_t name[64]; swprintf_s(name, L"\\rpi5fan-%04u-%02u-%02u.csv", t.wYear, t.wMonth, t.wDay);
        auto path = std::filesystem::path(dir + name);
        bool header = !std::filesystem::exists(path) || std::filesystem::file_size(path) == 0;
        std::ofstream f(path, std::ios::app | std::ios::binary);
        if (!f) { sample.logWarning = L"Cannot write the CSV log. Fan control is unaffected."; return; }
        if (header) f << "timestamp,temperature_c,temperature_valid,current_percent,requested_percent,mode,hardware_ready,temp_provider_ready,temp_provider_status,failsafe,overtemp,temp_failures,rpm,event\n";
        char stamp[80];
        sprintf_s(stamp, "%04u-%02u-%02uT%02u:%02u:%02u", t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond);
        f << stamp << ',';
        if (sample.connected) {
            const auto& s = sample.status;
            if (s.TemperatureValid) f << std::fixed << std::setprecision(1) << s.TemperatureMilliCelsius / 1000.0;
            f << ',' << s.TemperatureValid << ',' << s.CurrentPercent << ',' << s.RequestedPercent << ','
              << (s.ControlMode ? "manual" : "automatic") << ',' << s.HardwareReady << ','
              << s.TemperatureProviderReady << ",0x" << std::hex << std::setw(8) << std::setfill('0')
              << s.LastTemperatureProviderStatus << std::dec << ',' << s.FailSafeActive << ','
              << s.OverTemperatureOverride << ',' << s.ConsecutiveTemperatureFailures << ',';
            if (s.FanRpmValid) f << s.FanRpm;
            f << ',' << Csv(sample.event.empty() ? L"sample" : sample.event);
        } else {
            f << ",,,,,,,,,,,," << Csv(sample.error);
        }
        f << '\n'; f.flush();
        if (!f) sample.logWarning = L"CSV write failed. Fan control is unaffected.";
    } catch (...) { sample.logWarning = L"Logging error. Fan control is unaffected."; }
}
class Worker {
    HWND window_;
    std::thread thread_;
    std::mutex mutex_;
    std::condition_variable cv_;
    bool stop_ = false;
    int command_ = 0;
    unsigned percent_ = 50;
    Sample latest_;
    std::wstring directory_;
    void Run() {
        Device device;
        for (;;) {
            int command; unsigned percent;
            { std::lock_guard<std::mutex> lock(mutex_); if (stop_) break;
              command = command_; command_ = 0; percent = percent_; }
            Sample sample;
            try {
                if (command) {
                    device.Command(command, percent);
                    sample.event = command == AUTO ? L"Automatic selected" : command == FULL ? L"100% fail-safe selected" : L"Manual selected: " + std::to_wstring(percent) + L"%";
                }
                sample.status = device.Read(); sample.connected = true;
            } catch (const Failure& e) { device.Close(); sample.error = e.message; }
              catch (...) { device.Close(); sample.error = L"Unexpected driver error. No cooling state is assumed."; }
            LogSample(sample, directory_);
            { std::lock_guard<std::mutex> lock(mutex_); if (stop_) break; latest_ = sample; }
            PostMessageW(window_, WM_SAMPLE, 0, 0);
            std::unique_lock<std::mutex> lock(mutex_);
            cv_.wait_for(lock, std::chrono::seconds(2), [&] { return stop_ || command_ != 0; });
            if (stop_) break;
        }
    }
public:
    Worker(HWND h, const std::wstring& dir) : window_(h), directory_(dir) { thread_ = std::thread([this] { Run(); }); }
    ~Worker() {
        { std::lock_guard<std::mutex> lock(mutex_); stop_ = true; }
        cv_.notify_one();
        if (thread_.joinable()) { CancelSynchronousIo(thread_.native_handle()); thread_.join(); }
    }
    Sample Latest() { std::lock_guard<std::mutex> lock(mutex_); return latest_; }
    void Request(int command, unsigned percent) {
        { std::lock_guard<std::mutex> lock(mutex_); command_ = command; percent_ = percent; }
        cv_.notify_one();
    }
};
void Rounded(Graphics& g, RectF r, float radius, Color fill, Color edge) {
    GraphicsPath path; float d = radius * 2;
    path.AddArc(r.X,r.Y,d,d,180,90); path.AddArc(r.GetRight()-d,r.Y,d,d,270,90);
    path.AddArc(r.GetRight()-d,r.GetBottom()-d,d,d,0,90); path.AddArc(r.X,r.GetBottom()-d,d,d,90,90);
    path.CloseFigure(); SolidBrush b(fill); Pen p(edge,1); g.FillPath(&b,&path); g.DrawPath(&p,&path);
}
void Label(Graphics& g, const std::wstring& value, RectF r, float size, Color color,
           bool bold = false, StringAlignment alignment = StringAlignmentNear) {
    FontFamily family(L"Segoe UI"); Font font(&family,size,bold ? FontStyleBold : FontStyleRegular,UnitPixel);
    SolidBrush brush(color); StringFormat f; f.SetAlignment(alignment);
    f.SetTrimming(StringTrimmingEllipsisCharacter);
    g.DrawString(value.c_str(),-1,&font,r,&f,&brush);
}
struct App {
    HWND window = nullptr, slider = nullptr, log = nullptr;
    HFONT controlFont = nullptr;
    HBRUSH cardBrush = CreateSolidBrush(RGB(23,33,49));
    float scale = 1, width = 960, height = 760, leftWidth = 360, rightX = 408, rightWidth = 524;
    bool preview = false, snapshot = false, paused = false, pending = false, firstSample = true, motionAllowed = true;
    int exitCode = 0;
    unsigned manual = 50;
    std::wstring logDir;
    std::deque<std::wstring> recent;
    std::wstring lastError;
    Sample sample;
    Rotor rotor;
    Clock::time_point lastFrame = Clock::now(), lastSample = Clock::now();
    std::unique_ptr<Worker> worker;
    IStream* imageStream = nullptr;
    std::unique_ptr<Bitmap> fan;
    ~App() { worker.reset(); fan.reset(); if (imageStream) imageStream->Release();
             if (controlFont) DeleteObject(controlFont); DeleteObject(cardBrush); }
    bool LoadFan() {
        HMODULE module = GetModuleHandleW(nullptr);
        HRSRC r = FindResourceW(module, MAKEINTRESOURCEW(102), RT_RCDATA);
        if (!r) return false;
        HGLOBAL mem = LoadResource(module,r); DWORD bytes = SizeofResource(module,r);
        if (!mem || !bytes) return false;
        imageStream = SHCreateMemStream(static_cast<const BYTE*>(LockResource(mem)),bytes);
        if (!imageStream) return false;
        fan.reset(Bitmap::FromStream(imageStream));
        return fan && fan->GetLastStatus() == Ok && fan->GetWidth() == 128 && fan->GetHeight() == 128;
    }
    void MotionSettings() {
        BOOL enabled = TRUE; SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION,0,&enabled,0);
        HIGHCONTRASTW hc{sizeof(hc)}; SystemParametersInfoW(SPI_GETHIGHCONTRAST,sizeof(hc),&hc,0);
        motionAllowed = enabled && !(hc.dwFlags & HCF_HIGHCONTRASTON);
    }
    void Layout() {
        scale = GetDpiForWindow(window) / 96.0f;
        RECT r{}; GetClientRect(window,&r); width = r.right/scale; height = r.bottom/scale;
        leftWidth = (width - 76) * 0.405f; rightX = 28 + leftWidth + 20; rightWidth = width - rightX - 28;
        if (controlFont) DeleteObject(controlFont);
        controlFont = CreateFontW(-static_cast<int>(13*scale),0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
            DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,CLEARTYPE_QUALITY,DEFAULT_PITCH,L"Segoe UI");
        auto place = [&](int id, float x,float y,float w,float h) {
            HWND child = GetDlgItem(window,id); MoveWindow(child,static_cast<int>(x*scale),static_cast<int>(y*scale),
                static_cast<int>(w*scale),static_cast<int>(h*scale),TRUE); SendMessageW(child,WM_SETFONT,reinterpret_cast<WPARAM>(controlFont),TRUE);
        };
        float bw = (rightWidth-64)/3;
        place(AUTO,rightX+16,334,bw,38); place(MANUAL,rightX+32+bw,334,bw,38);
        place(FULL,rightX+48+bw*2,334,bw,38);
        place(SLIDER,rightX+16,388,rightWidth-125,28);
        place(PAUSE,28+leftWidth-114,130,96,28);
        place(LOGS,width-154,568,108,30);
        place(LOGVIEW,44,610,width-88,std::max(70.0f,height-660));
        InvalidateRect(window,nullptr,FALSE);
    }
    void EnableControls() {
        bool ready = sample.connected && sample.status.HardwareReady && !pending && !preview;
        for (int id : {AUTO,MANUAL,FULL,SLIDER}) EnableWindow(GetDlgItem(window,id),ready);
    }
    void AddRecent(const std::wstring& text) {
        SYSTEMTIME t{}; GetLocalTime(&t); wchar_t b[32]; swprintf_s(b,L"%02u:%02u:%02u  ",t.wHour,t.wMinute,t.wSecond);
        recent.push_back(std::wstring(b)+text); while (recent.size()>120) recent.pop_front();
        std::wstring all; for (const auto& s : recent) all += s+L"\r\n";
        SetWindowTextW(log,all.c_str()); SendMessageW(log,EM_SETSEL,all.size(),all.size()); SendMessageW(log,EM_SCROLLCARET,0,0);
    }
    void AcceptSample() {
        sample = worker->Latest(); pending = false; lastSample = Clock::now();
        if (sample.connected) {
            if (firstSample && sample.status.RequestedPercent >= 30 && sample.status.RequestedPercent <= 100) {
                manual = sample.status.RequestedPercent; SendMessageW(slider,TBM_SETPOS,TRUE,manual);
            }
            firstSample = false; lastError.clear();
            wchar_t line[256]; auto& s = sample.status;
            swprintf_s(line,L"PWM %lu%% | %s | Temperature %s | Provider %s | Safe %lu | Overtemp %lu | Failures %lu",
                s.CurrentPercent,s.ControlMode ? L"Manual" : L"Automatic",s.TemperatureValid ? L"valid" : L"unavailable",
                s.TemperatureProviderReady ? L"ready" : L"unavailable",s.FailSafeActive,s.OverTemperatureOverride,s.ConsecutiveTemperatureFailures);
            AddRecent(sample.event.empty() ? line : sample.event);
        } else if (sample.error != lastError) { AddRecent(sample.error); lastError = sample.error; }
        if (!sample.logWarning.empty()) AddRecent(sample.logWarning);
        if (!sample.connected || !sample.status.HardwareReady ||
            (sample.status.FanRpmValid && sample.status.FanRpm == 0) || sample.status.CurrentPercent == 0) rotor.Stop();
        EnableControls(); InvalidateRect(window,nullptr,FALSE);
        for (int id : {AUTO,MANUAL,FULL}) InvalidateRect(GetDlgItem(window,id),nullptr,TRUE);
    }
    std::pair<std::wstring,std::wstring> Safety(Color& color) {
        color = Accent; const auto& s = sample.status;
        if (preview) { color = Warning; return {L"PREVIEW ONLY - simulated readings",L"No driver is opened and no fan-control command is sent in preview mode."}; }
        if (!sample.connected) { color = Danger; return {L"Fan state is unknown - check the physical cooler",sample.error.empty() ? L"Connecting to the installed exp.6 API v2 fan driver..." : sample.error}; }
        if (!s.HardwareReady) { color = Warning; return {L"Fan hardware is not ready",L"Windows has not reported PWM control. Do not assume that cooling is working."}; }
        if (s.OverTemperatureOverride) { color = Danger; return {L"Over-temperature override active",L"The driver reports a 100% cooling override. Check airflow and temperature."}; }
        if (!s.TemperatureProviderReady || !s.TemperatureValid || s.FailSafeActive) {
            color = Warning; return {L"Temperature / fail-safe warning",L"The driver's safety policy remains authoritative. See provider and fail-safe details below."}; }
        if (s.FanRpmValid && s.FanRpm == 0 && s.CurrentPercent > 0) {
            color = Danger; return {L"Tachometer reports 0 RPM",L"PWM is nonzero, but rotation is not detected. Check the physical fan and its connection."}; }
        return {L"Driver control is active",L"Closing this GUI leaves the driver's current mode in place. Select Automatic for temperature-based control."};
    }
    void Draw(Graphics& g) {
        g.Clear(Background); g.SetSmoothingMode(SmoothingModeAntiAlias);
        g.SetTextRenderingHint(TextRenderingHintClearTypeGridFit); g.ScaleTransform(scale,scale);
        Label(g,L"Raspberry Pi 5",RectF(28,22,width-290,42),30,Text,true);
        Label(g,L"FAN CONTROL  /  STANDALONE",RectF(29,67,450,24),12,Muted,true);
        Color state = sample.connected && sample.status.HardwareReady ? Accent : Warning;
        if (preview) state = Warning;
        Rounded(g,RectF(width-229,32,201,36),18,Card,Edge);
        SolidBrush dot(state); g.FillEllipse(&dot,RectF(width-213,46,8,8));
        Label(g,preview ? L"PREVIEW" : sample.connected && sample.status.HardwareReady ? L"DRIVER READY" : L"NOT CONNECTED",
              RectF(width-196,40,161,25),12,state,true);
        Rounded(g,RectF(28,116,leftWidth,330),18,Card,Edge);
        Label(g,L"ACTIVE COOLER",RectF(48,138,leftWidth-144,25),12,Muted,true);
        float cx=28+leftWidth/2, cy=274;
        SolidBrush disc(Color(255,18,29,44)); g.FillEllipse(&disc,RectF(cx-106,cy-106,212,212));
        Pen ring(Edge,2); g.DrawEllipse(&ring,RectF(cx-108,cy-108,216,216));
        if (sample.connected && sample.status.HardwareReady) {
            Pen arc(Accent,3); arc.SetStartCap(LineCapRound); arc.SetEndCap(LineCapRound);
            g.DrawArc(&arc,RectF(cx-108,cy-108,216,216),-90.0f,static_cast<float>(sample.status.CurrentPercent)*3.6f);
        }
        GraphicsState saved=g.Save(); g.TranslateTransform(cx,cy); g.RotateTransform(static_cast<float>(rotor.angle));
        ColorMatrix matrix{}; matrix.m[3][3] = sample.connected ? 1.0f : 0.3f;
        matrix.m[4][0]=93.0f/255; matrix.m[4][1]=228.0f/255; matrix.m[4][2]=199.0f/255; matrix.m[4][4]=1;
        ImageAttributes tint; tint.SetColorMatrix(&matrix);
        g.SetInterpolationMode(InterpolationModeHighQualityBicubic); g.SetPixelOffsetMode(PixelOffsetModeHighQuality);
        // Center on the uploaded image's hub rather than its slightly asymmetric bounding box.
        constexpr float size=172;
        g.DrawImage(fan.get(),RectF(-size*(64.502f/128),-size*(63.869f/128),size,size),0,0,128,128,UnitPixel,&tint);
        g.Restore(saved);
        Label(g,sample.connected ? std::to_wstring(sample.status.CurrentPercent)+L"% PWM" : L"-- PWM",
            RectF(40,390,leftWidth-24,34),24,Text,true,StringAlignmentCenter);
        std::wstring caption = sample.connected && sample.status.FanRpmValid
            ? std::to_wstring(sample.status.FanRpm)+L" RPM measured / animation scaled"
            : L"PWM illustration / RPM not available";
        if (paused || !motionAllowed) caption = L"Visual paused / fan control unchanged";
        Label(g,caption,RectF(40,425,leftWidth-24,19),10.5f,Muted,false,StringAlignmentCenter);
        Rounded(g,RectF(rightX,116,rightWidth,150),18,Card,Edge);
        Label(g,L"CPU TEMPERATURE",RectF(rightX+20,137,rightWidth-40,24),12,Muted,true);
        std::wstring temperature=L"--"; Color tc=Text;
        if (sample.connected && sample.status.TemperatureValid) {
            wchar_t b[40]; swprintf_s(b,L"%.1f \u00b0C",sample.status.TemperatureMilliCelsius/1000.0); temperature=b;
            if (sample.status.TemperatureMilliCelsius>=85000) tc=Danger;
            else if (sample.status.TemperatureMilliCelsius>=70000) tc=Warning;
        }
        Label(g,temperature,RectF(rightX+18,164,rightWidth-40,65),44,tc,true);
        wchar_t provider[150]; swprintf_s(provider,L"Temperature provider: %s  /  status 0x%08lX",
            sample.connected && sample.status.TemperatureProviderReady ? L"ready" : L"unavailable",sample.status.LastTemperatureProviderStatus);
        Label(g,provider,RectF(rightX+20,237,rightWidth-40,23),11,Muted);
        Rounded(g,RectF(rightX,284,rightWidth,162),18,Card,Edge);
        std::wstring mode=sample.connected ? sample.status.ControlMode ? L"MANUAL" : L"AUTOMATIC" : L"UNAVAILABLE";
        Label(g,L"CONTROL MODE  /  "+mode,RectF(rightX+20,303,rightWidth-40,25),12,Muted,true);
        Label(g,std::to_wstring(manual)+L"%",RectF(rightX+rightWidth-101,387,78,30),20,Text,true,StringAlignmentCenter);
        Label(g,L"30-100% / slider changes apply only with Apply manual",RectF(rightX+20,422,rightWidth-40,20),10.5f,Muted);
        Color safeColor; auto safe=Safety(safeColor);
        Rounded(g,RectF(28,466,width-56,70),14,Card,safeColor);
        Label(g,safe.first,RectF(46,479,width-92,25),13,safeColor,true);
        Label(g,safe.second,RectF(46,506,width-92,24),11.5f,Muted);
        Rounded(g,RectF(28,554,width-56,std::max(143.0f,height-596)),16,Card,Edge);
        Label(g,L"STATUS & RECENT ACTIVITY",RectF(46,576,width-235,26),12,Muted,true);
        Label(g,sample.logWarning.empty() ? L"Logs: %LOCALAPPDATA%\\Rpi5Fan\\Logs  /  No runtime install. No driver installation or firmware changes." : sample.logWarning,
            RectF(29,height-28,width-58,22),10.5f,sample.logWarning.empty() ? Muted : Warning);
    }
    void Paint(HDC dc) {
        RECT r{}; GetClientRect(window,&r); if (r.right<=0 || r.bottom<=0) return;
        HDC memory=CreateCompatibleDC(dc); HBITMAP bmp=CreateCompatibleBitmap(dc,r.right,r.bottom);
        if (!memory || !bmp) { if (memory) DeleteDC(memory); if (bmp) DeleteObject(bmp); return; }
        HGDIOBJ previous=SelectObject(memory,bmp);
        { Graphics g(memory); Draw(g); }
        BitBlt(dc,0,0,r.right,r.bottom,memory,0,0,SRCCOPY);
        SelectObject(memory,previous); DeleteObject(bmp); DeleteDC(memory);
    }
    void DrawButton(const DRAWITEMSTRUCT& d) {
        Graphics g(d.hDC); g.SetSmoothingMode(SmoothingModeAntiAlias);
        float w=static_cast<float>(d.rcItem.right-d.rcItem.left), h=static_cast<float>(d.rcItem.bottom-d.rcItem.top);
        bool disabled=(d.itemState&ODS_DISABLED)!=0;
        bool selected=sample.connected && ((d.CtlID==AUTO && !sample.status.ControlMode) || (d.CtlID==MANUAL && sample.status.ControlMode));
        Color fill=selected ? Color(255,31,75,71) : Card;
        if (d.itemState&ODS_SELECTED) fill=Color(255,40,68,83);
        Rounded(g,RectF(1,1,w-2,h-2),7*scale,fill,disabled ? Edge : d.CtlID==FULL ? Warning : selected ? Accent : Edge);
        wchar_t title[100]; GetWindowTextW(d.hwndItem,title,100);
        Label(g,title,RectF(3,(h-17*scale)/2,w-6,22*scale),12*scale,disabled ? Muted : Text,false,StringAlignmentCenter);
        if (d.itemState&ODS_FOCUS) { RECT r=d.rcItem; InflateRect(&r,-4,-4); DrawFocusRect(d.hDC,&r); }
    }
    bool SaveSnapshot() {
        RECT r{}; GetClientRect(window,&r); Bitmap b(r.right,r.bottom,PixelFormat32bppARGB);
        { Graphics g(&b); HDC dc=g.GetHDC();
          SendMessageW(window,WM_PRINT,reinterpret_cast<WPARAM>(dc),PRF_CLIENT|PRF_CHILDREN|PRF_ERASEBKGND);
          g.ReleaseHDC(dc); }
        UINT count=0,bytes=0; GetImageEncodersSize(&count,&bytes); std::vector<BYTE> buffer(bytes);
        if (!bytes) return false;
        auto enc=reinterpret_cast<ImageCodecInfo*>(buffer.data()); GetImageEncoders(count,bytes,enc);
        for (UINT i=0;i<count;++i) if (wcscmp(enc[i].MimeType,L"image/png")==0)
            return b.Save(L"preview.png",&enc[i].Clsid,nullptr)==Ok;
        return false;
    }
};
LRESULT CALLBACK WindowProc(HWND h,UINT msg,WPARAM wp,LPARAM lp) {
    App* a=reinterpret_cast<App*>(GetWindowLongPtrW(h,GWLP_USERDATA));
    if (msg==WM_NCCREATE) { a=static_cast<App*>(reinterpret_cast<CREATESTRUCTW*>(lp)->lpCreateParams);
        a->window=h; SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(a)); }
    if (!a) return DefWindowProcW(h,msg,wp,lp);
    switch (msg) {
    case WM_CREATE: {
        auto control=[&](const wchar_t* cls,const wchar_t* text,DWORD style,int id) {
            return CreateWindowExW(0,cls,text,WS_CHILD|WS_VISIBLE|style,0,0,1,1,h,reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),GetModuleHandleW(nullptr),nullptr);
        };
        control(L"BUTTON",L"Automatic",BS_OWNERDRAW|WS_TABSTOP,AUTO);
        control(L"BUTTON",L"Apply manual",BS_OWNERDRAW|WS_TABSTOP,MANUAL);
        control(L"BUTTON",L"Force 100%",BS_OWNERDRAW|WS_TABSTOP,FULL);
        control(L"BUTTON",L"Pause visual",BS_OWNERDRAW|WS_TABSTOP,PAUSE);
        control(L"BUTTON",L"Open logs",BS_OWNERDRAW|WS_TABSTOP,LOGS);
        a->slider=control(TRACKBAR_CLASSW,L"Manual fan percentage",TBS_HORZ|TBS_NOTICKS|WS_TABSTOP,SLIDER);
        SendMessageW(a->slider,TBM_SETRANGE,TRUE,MAKELPARAM(30,100)); SendMessageW(a->slider,TBM_SETPOS,TRUE,50);
        a->log=control(L"EDIT",L"",ES_MULTILINE|ES_READONLY|ES_AUTOVSCROLL|WS_VSCROLL|WS_TABSTOP,LOGVIEW);
        SendMessageW(a->log,EM_SETLIMITTEXT,60000,0);
        a->MotionSettings(); a->Layout();
        if (a->preview) {
            auto& s=a->sample; s.connected=true; s.status.Size=sizeof(s.status); s.status.ApiVersion=2;
            s.status.HardwareReady=1; s.status.TemperatureProviderReady=1; s.status.TemperatureValid=1;
            s.status.TemperatureMilliCelsius=52400; s.status.CurrentPercent=40; s.status.RequestedPercent=40;
            a->AddRecent(L"PREVIEW: simulated 52.4 C / 40% PWM / Automatic. No driver access.");
        } else { a->logDir=LogDirectory(); a->worker=std::make_unique<Worker>(h,a->logDir); }
        a->EnableControls(); SetTimer(h,1,16,nullptr);
        if (a->snapshot) SetTimer(h,2,1000,nullptr);
        return 0;
    }
    case WM_SAMPLE: if (a->worker) a->AcceptSample(); return 0;
    case WM_SIZE: a->Layout(); a->lastFrame=Clock::now(); return 0;
    case WM_DPICHANGED: { const RECT* r=reinterpret_cast<RECT*>(lp); SetWindowPos(h,nullptr,r->left,r->top,r->right-r->left,r->bottom-r->top,SWP_NOZORDER|SWP_NOACTIVATE); a->Layout(); return 0; }
    case WM_GETMINMAXINFO: { auto m=reinterpret_cast<MINMAXINFO*>(lp); UINT dpi=GetDpiForWindow(h); if (!dpi) dpi=96;
        RECT r{0,0,MulDiv(900,dpi,96),MulDiv(730,dpi,96)};
        AdjustWindowRectExForDpi(&r,WS_OVERLAPPEDWINDOW,FALSE,WS_EX_CONTROLPARENT,dpi);
        m->ptMinTrackSize={r.right-r.left,r.bottom-r.top}; return 0; }
    case WM_SETTINGCHANGE: a->MotionSettings(); return 0;
    case WM_TIMER: {
        if (wp==2) { KillTimer(h,2); a->exitCode=a->SaveSnapshot() ? 0 : 12; PostMessageW(h,WM_CLOSE,0,0); return 0; }
        auto now=Clock::now(); double dt=std::chrono::duration<double>(now-a->lastFrame).count(); a->lastFrame=now;
        if (!a->preview && a->sample.connected && now-a->lastSample > std::chrono::seconds(6)) {
            a->sample.connected=false;
            a->sample.error=L"No fresh driver status for over 6 seconds. Cooling state is unknown; check the physical fan.";
            a->rotor.Stop(); a->EnableControls(); a->AddRecent(a->sample.error);
            InvalidateRect(h,nullptr,FALSE);
        }
        if (IsIconic(h)||a->paused||!a->motionAllowed) return 0;
        const auto& s=a->sample.status;
        double target=VisualSpeed(a->sample.connected && s.HardwareReady,s.CurrentPercent,s.FanRpmValid!=0,s.FanRpm);
        if (target==0) { a->rotor.Stop(); return 0; }
        a->rotor.Step(std::min(dt,0.1),target);
        RECT r{static_cast<LONG>((28+a->leftWidth/2-110)*a->scale),static_cast<LONG>(164*a->scale),
               static_cast<LONG>((28+a->leftWidth/2+110)*a->scale),static_cast<LONG>(384*a->scale)};
        InvalidateRect(h,&r,FALSE); return 0;
    }
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: { PAINTSTRUCT ps; HDC dc=BeginPaint(h,&ps); a->Paint(dc); EndPaint(h,&ps); return 0; }
    case WM_PRINTCLIENT: a->Paint(reinterpret_cast<HDC>(wp)); return 0;
    case WM_DRAWITEM: a->DrawButton(*reinterpret_cast<DRAWITEMSTRUCT*>(lp)); return TRUE;
    case WM_CTLCOLORSTATIC:
    case WM_CTLCOLOREDIT: SetBkColor(reinterpret_cast<HDC>(wp),RGB(23,33,49)); SetTextColor(reinterpret_cast<HDC>(wp),RGB(148,166,190)); return reinterpret_cast<LRESULT>(a->cardBrush);
    case WM_NOTIFY: {
        auto n=reinterpret_cast<NMHDR*>(lp);
        if (n->idFrom==SLIDER && n->code==NM_CUSTOMDRAW) {
            auto d=reinterpret_cast<NMCUSTOMDRAW*>(lp);
            if (d->dwDrawStage==CDDS_PREPAINT) return CDRF_NOTIFYITEMDRAW;
            if (d->dwDrawStage==CDDS_ITEMPREPAINT && (d->dwItemSpec==TBCD_CHANNEL || d->dwItemSpec==TBCD_THUMB)) {
                Graphics g(d->hdc); g.SetSmoothingMode(SmoothingModeAntiAlias); SolidBrush b(d->dwItemSpec==TBCD_THUMB ? Accent : Edge);
                float x=static_cast<float>(d->rc.left),y=static_cast<float>(d->rc.top),w=static_cast<float>(d->rc.right-d->rc.left),ht=static_cast<float>(d->rc.bottom-d->rc.top);
                if (d->dwItemSpec==TBCD_THUMB) g.FillEllipse(&b,x,y+(ht-w)/2,w,w);
                else g.FillRectangle(&b,x,y+ht/2-2*a->scale,w,4*a->scale);
                return CDRF_SKIPDEFAULT;
            }
        }
        break;
    }
    case WM_HSCROLL: a->manual=static_cast<unsigned>(SendMessageW(a->slider,TBM_GETPOS,0,0)); InvalidateRect(h,nullptr,FALSE); return 0;
    case WM_COMMAND: {
        int id=LOWORD(wp);
        if (id==PAUSE) { a->paused=!a->paused; a->rotor.Stop(); SetWindowTextW(GetDlgItem(h,PAUSE),a->paused ? L"Resume visual" : L"Pause visual"); InvalidateRect(h,nullptr,FALSE); }
        else if (id==LOGS) { if (a->preview) MessageBoxW(h,L"Preview mode does not create logs or contact the driver.",L"Preview",MB_OK); else if (!a->logDir.empty()) ShellExecuteW(h,L"open",a->logDir.c_str(),nullptr,nullptr,SW_SHOWNORMAL); }
        else if ((id==AUTO||id==MANUAL||id==FULL) && a->worker && a->sample.connected && a->sample.status.HardwareReady && !a->pending) {
            a->pending=true; a->EnableControls(); a->worker->Request(id,a->manual);
        }
        return 0;
    }
    case WM_CLOSE: KillTimer(h,1); KillTimer(h,2); a->worker.reset(); DestroyWindow(h); return 0;
    case WM_DESTROY: PostQuitMessage(a->exitCode); return 0;
    }
    return DefWindowProcW(h,msg,wp,lp);
}
int WINAPI wWinMain(HINSTANCE instance,HINSTANCE,LPWSTR,int show) {
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    bool selftest=false, preview=false, snapshot=false;
    int count=0; LPWSTR* args=CommandLineToArgvW(GetCommandLineW(),&count);
    for (int i=1;args && i<count;++i) {
        if (wcscmp(args[i],L"--self-test")==0) selftest=true;
        else if (wcscmp(args[i],L"--preview")==0) preview=true;
        else if (wcscmp(args[i],L"--snapshot")==0) { preview=true; snapshot=true; }
    }
    if (args) LocalFree(args);
    if (!selftest && !preview && !IsUserAnAdmin()) {
        wchar_t exe[32768]; GetModuleFileNameW(nullptr,exe,32768);
        SHELLEXECUTEINFOW info{sizeof(info)}; info.lpVerb=L"runas"; info.lpFile=exe; info.nShow=SW_SHOWNORMAL;
        if (!ShellExecuteExW(&info)) { MessageBoxW(nullptr,L"Administrator access is needed to open the installed fan driver. No fan setting was changed.",L"Raspberry Pi 5 Fan Control",MB_OK|MB_ICONINFORMATION); return 5; }
        return 0;
    }
    GdiplusStartupInput input; ULONG_PTR token=0;
    if (GdiplusStartup(&token,&input,nullptr)!=Ok) return 2;
    CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    int result=0;
    {
        App app; app.preview=preview; app.snapshot=snapshot;
        if (!app.LoadFan()) { MessageBoxW(nullptr,L"Embedded fan image could not be decoded.",L"Fan Control",MB_OK|MB_ICONERROR); result=3; }
        else if (selftest) result=TestAnimation() ? 0 : 10;
        else {
            INITCOMMONCONTROLSEX controls{sizeof(controls),ICC_BAR_CLASSES|ICC_STANDARD_CLASSES}; InitCommonControlsEx(&controls);
            WNDCLASSEXW wc{sizeof(wc)}; wc.lpfnWndProc=WindowProc; wc.hInstance=instance;
            wc.hCursor=LoadCursorW(nullptr,IDC_ARROW); wc.lpszClassName=L"Rpi5FanControlStandalone";
            wc.hIcon=LoadIconW(instance,MAKEINTRESOURCEW(101)); wc.hIconSm=wc.hIcon;
            if (!RegisterClassExW(&wc)) result=4;
            else {
                UINT dpi=GetDpiForSystem(); RECT r{0,0,MulDiv(960,dpi,96),MulDiv(760,dpi,96)};
                AdjustWindowRectExForDpi(&r,WS_OVERLAPPEDWINDOW,FALSE,WS_EX_CONTROLPARENT,dpi);
                HWND h=CreateWindowExW(WS_EX_CONTROLPARENT,wc.lpszClassName,L"Raspberry Pi 5 Fan Control - Standalone",
                    WS_OVERLAPPEDWINDOW|WS_CLIPCHILDREN,CW_USEDEFAULT,CW_USEDEFAULT,r.right-r.left,r.bottom-r.top,nullptr,nullptr,instance,&app);
                if (!h) result=6;
                else { ShowWindow(h,show); UpdateWindow(h); MSG message{};
                    while (GetMessageW(&message,nullptr,0,0)>0) if (!IsDialogMessageW(h,&message)) { TranslateMessage(&message); DispatchMessageW(&message); }
                    result=static_cast<int>(message.wParam);
                }
            }
        }
    }
    CoUninitialize(); GdiplusShutdown(token); return result;
}
