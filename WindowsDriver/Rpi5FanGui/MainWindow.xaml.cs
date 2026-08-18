using System.Globalization;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Threading;

namespace Rpi5FanControl;

public partial class MainWindow : Window
{
    private readonly DriverClient _driver = new();
    private readonly DispatcherTimer _timer;
    private readonly string _logDirectory;
    private bool _reportedConnection;

    public MainWindow()
    {
        InitializeComponent();

        _logDirectory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Rpi5Fan",
            "Logs");
        Directory.CreateDirectory(_logDirectory);
        UpdateLogPathText();

        _timer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(2)
        };
        _timer.Tick += (_, _) => RefreshStatus();

        Loaded += (_, _) =>
        {
            RefreshStatus();
            _timer.Start();
        };
        Closed += (_, _) =>
        {
            _timer.Stop();
            _driver.Dispose();
        };
    }

    private void RefreshStatus()
    {
        try
        {
            _driver.Connect();
            if (!_reportedConnection)
            {
                AppendEvent("driver-connected");
                _reportedConnection = true;
            }

            DriverStatus status = _driver.GetStatus();
            UpdateDashboard(status);
            AppendStatus(status, "sample");
        }
        catch (Exception ex)
        {
            _reportedConnection = false;
            DriverText.Text = "Unavailable";
            TempProviderText.Text = "Provider: unavailable";
            TemperatureText.Text = "--";
            FanPercentText.Text = "--";
            ModeText.Text = "--";
            SafetyText.Text = "Fan driver unavailable. Verify the physical fan is still spinning. UEFI hands Windows a 100% fan state, but an abrupt kernel failure cannot run driver cleanup.";
            AddRecent($"{DateTime.Now:HH:mm:ss} ERROR {ex.Message}");
            TryAppendRawError(ex.Message);
            _driver.Dispose();
        }
    }

    private void UpdateDashboard(DriverStatus status)
    {
        DriverText.Text = status.HardwareReady != 0 ? "Ready" : "Loaded";
        TempProviderText.Text = status.TemperatureProviderReady != 0
            ? $"Provider: ready (API {status.TemperatureProviderApiVersion})"
            : $"Provider: unavailable (0x{status.LastTemperatureProviderStatus:X8})";
        TemperatureText.Text = status.TemperatureValid != 0
            ? $"{status.TemperatureMilliCelsius / 1000.0:F1} °C"
            : "--";
        FanPercentText.Text = $"{status.CurrentPercent}%";
        ModeText.Text = status.ControlMode == (uint)FanControlMode.Manual
            ? "Manual"
            : "Automatic";

        if (status.HardwareReady == 0)
        {
            SafetyText.Text = "Fan hardware is not ready; Windows has not taken PWM control.";
        }
        else if (status.TemperatureProviderReady == 0)
        {
            SafetyText.Text = $"Temperature provider unavailable — fan forced to 100% (provider status 0x{status.LastTemperatureProviderStatus:X8}).";
        }
        else if (status.OverTemperatureOverride != 0)
        {
            SafetyText.Text = "OVER-TEMPERATURE override active — fan forced to 100%.";
        }
        else if (status.FailSafeActive != 0 && status.TemperatureValid == 0)
        {
            SafetyText.Text = $"Temperature fail-safe active — fan forced to 100% (failures: {status.ConsecutiveTemperatureFailures}).";
        }
        else if (status.FailSafeActive != 0)
        {
            SafetyText.Text = "Fail-safe active — fan forced to 100%.";
        }
        else
        {
            SafetyText.Text = "Normal split-driver control active. The driver will never intentionally command less than 30%.";
        }

        FooterText.Text = status.FanRpmValid != 0
            ? $"Measured fan speed: {status.FanRpm} RPM"
            : "Actual fan RPM is not reported yet because tachometer input is not implemented in the driver.";
    }

    private void Automatic_Click(object sender, RoutedEventArgs e)
    {
        RunControlAction(() => _driver.SetAutomatic(), "automatic-selected");
    }

    private void Manual_Click(object sender, RoutedEventArgs e)
    {
        uint percent = (uint)Math.Round(ManualSlider.Value);
        RunControlAction(() => _driver.SetManual(percent), $"manual-selected-{percent}%");
    }

    private void FailSafe_Click(object sender, RoutedEventArgs e)
    {
        RunControlAction(() => _driver.SetFailSafe100(), "force-100%-selected");
    }

    private void RunControlAction(Action action, string eventName)
    {
        try
        {
            _driver.Connect();
            action();
            AppendEvent(eventName);
            RefreshStatus();
        }
        catch (Exception ex)
        {
            AppendEvent($"control-error:{ex.Message}");
            MessageBox.Show(
                this,
                ex.Message,
                "Raspberry Pi 5 Fan Control",
                MessageBoxButton.OK,
                MessageBoxImage.Error);
        }
    }

    private void ManualSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (ManualValueText != null)
        {
            ManualValueText.Text = $"{Math.Round(e.NewValue):0}%";
        }
    }

    private void AppendStatus(DriverStatus status, string eventName)
    {
        string temperature = status.TemperatureValid != 0
            ? (status.TemperatureMilliCelsius / 1000.0).ToString("F1", CultureInfo.InvariantCulture)
            : string.Empty;
        string mode = status.ControlMode == (uint)FanControlMode.Manual ? "manual" : "automatic";
        string line = string.Join(",",
            DateTimeOffset.Now.ToString("O", CultureInfo.InvariantCulture),
            temperature,
            status.TemperatureValid,
            status.CurrentPercent,
            status.RequestedPercent,
            mode,
            status.HardwareReady,
            status.TemperatureProviderReady,
            $"0x{status.LastTemperatureProviderStatus:X8}",
            status.FailSafeActive,
            status.OverTemperatureOverride,
            status.ConsecutiveTemperatureFailures,
            status.FanRpmValid != 0 ? status.FanRpm.ToString(CultureInfo.InvariantCulture) : string.Empty,
            EscapeCsv(eventName));

        AppendCsvLine(line);
        AddRecent(
            $"{DateTime.Now:HH:mm:ss}  Temp={(temperature.Length == 0 ? "--" : temperature + "C"),6}  " +
            $"Fan={status.CurrentPercent,3}%  Mode={mode,-9}  TempDrv={status.TemperatureProviderReady}  Safe={status.FailSafeActive}  {eventName}");
    }

    private void AppendEvent(string eventName)
    {
        string line = string.Join(",",
            DateTimeOffset.Now.ToString("O", CultureInfo.InvariantCulture),
            string.Empty, string.Empty, string.Empty, string.Empty, string.Empty,
            string.Empty, string.Empty, string.Empty, string.Empty, string.Empty,
            string.Empty, string.Empty,
            EscapeCsv(eventName));
        AppendCsvLine(line);
        AddRecent($"{DateTime.Now:HH:mm:ss}  {eventName}");
    }

    private void TryAppendRawError(string message)
    {
        try
        {
            AppendEvent($"driver-error:{message}");
        }
        catch
        {
            // Logging must never make fan-control diagnostics fail harder.
        }
    }

    private void AppendCsvLine(string line)
    {
        string path = GetCurrentLogPath();
        if (!File.Exists(path))
        {
            File.WriteAllText(
                path,
                "timestamp,temperature_c,temperature_valid,current_percent,requested_percent,mode,hardware_ready,temp_provider_ready,temp_provider_status,failsafe,overtemp,temp_failures,rpm,event" + Environment.NewLine,
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        }
        File.AppendAllText(path, line + Environment.NewLine, new UTF8Encoding(false));
        UpdateLogPathText();
    }

    private string GetCurrentLogPath() =>
        Path.Combine(_logDirectory, $"rpi5fan-{DateTime.Now:yyyy-MM-dd}.csv");

    private void UpdateLogPathText()
    {
        LogPathText.Text = $"Log file: {GetCurrentLogPath()}";
    }

    private void AddRecent(string text)
    {
        RecentLogList.Items.Add(text);
        while (RecentLogList.Items.Count > 200)
        {
            RecentLogList.Items.RemoveAt(0);
        }
        RecentLogList.ScrollIntoView(RecentLogList.Items[^1]);
    }

    private static string EscapeCsv(string value) =>
        $"\"{value.Replace("\"", "\"\"")}\"";
}
