using System.Globalization;
using System.IO;
using System.Text;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace Rpi5FanControl;

public partial class MainWindow : Window
{
    private static readonly Brush HealthyBrush = BrushFrom("#52E0A4");
    private static readonly Brush WarningBrush = BrushFrom("#FFB454");
    private static readonly Brush DangerBrush = BrushFrom("#FF6B7B");
    private static readonly Brush MutedBrush = BrushFrom("#7185A4");
    private static readonly Brush SafetyHealthyBackground = BrushFrom("#15362E");
    private static readonly Brush SafetyHealthyBorder = BrushFrom("#2E7B68");
    private static readonly Brush SafetyWarningBackground = BrushFrom("#3A2B16");
    private static readonly Brush SafetyWarningBorder = BrushFrom("#8C6728");
    private static readonly Brush SafetyDangerBackground = BrushFrom("#3A1820");
    private static readonly Brush SafetyDangerBorder = BrushFrom("#8F3545");

    private readonly DriverClient _driver = new();
    private readonly DispatcherTimer _timer;
    private readonly string _logDirectory;
    private bool _reportedConnection;
    private uint? _lastAnimatedPercent;
    private bool _fanAnimationRunning;

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
            StopFanAnimation();
            _driver.Dispose();
        };
    }

    private static SolidColorBrush BrushFrom(string hex)
    {
        var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(hex));
        brush.Freeze();
        return brush;
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
            DriverText.Foreground = DangerBrush;
            DriverIndicator.Fill = DangerBrush;
            TempProviderText.Text = "Unavailable";
            TempProviderText.Foreground = DangerBrush;
            TempProviderIndicator.Fill = DangerBrush;
            TemperatureText.Text = "--";
            TemperatureText.Foreground = MutedBrush;
            FanPercentText.Text = "--";
            ModeText.Text = "--";
            SetConnectionState(false);
            SetSafetyState(
                SafetyVisualState.Danger,
                "Fan driver unavailable. Verify the physical fan is still spinning; the UEFI fail-safe handoff is 100%.");
            StopFanAnimation();
            AddRecent($"{DateTime.Now:HH:mm:ss} ERROR {ex.Message}");
            TryAppendRawError(ex.Message);
            _driver.Dispose();
        }
    }

    private void UpdateDashboard(DriverStatus status)
    {
        bool hardwareReady = status.HardwareReady != 0;
        bool providerReady = status.TemperatureProviderReady != 0;

        DriverText.Text = hardwareReady ? "Ready" : "Loaded";
        DriverText.Foreground = hardwareReady ? HealthyBrush : WarningBrush;
        DriverIndicator.Fill = hardwareReady ? HealthyBrush : WarningBrush;

        TempProviderText.Text = providerReady
            ? $"Ready · API {status.TemperatureProviderApiVersion}"
            : $"Unavailable · 0x{status.LastTemperatureProviderStatus:X8}";
        TempProviderText.Foreground = providerReady ? HealthyBrush : WarningBrush;
        TempProviderIndicator.Fill = providerReady ? HealthyBrush : WarningBrush;

        TemperatureText.Text = status.TemperatureValid != 0
            ? $"{status.TemperatureMilliCelsius / 1000.0:F1} °C"
            : "--";
        TemperatureText.Foreground = status.TemperatureValid == 0
            ? MutedBrush
            : status.TemperatureMilliCelsius >= 85000u
                ? DangerBrush
                : status.TemperatureMilliCelsius >= 70000u
                    ? WarningBrush
                    : Brushes.White;

        FanPercentText.Text = $"{status.CurrentPercent}%";
        ModeText.Text = status.ControlMode == (uint)FanControlMode.Manual
            ? "Manual"
            : "Automatic";

        SetConnectionState(hardwareReady);
        UpdateFanAnimation(status.CurrentPercent, hardwareReady);

        if (!hardwareReady)
        {
            SetSafetyState(SafetyVisualState.Warning,
                "Fan hardware is not ready; Windows has not taken PWM control.");
        }
        else if (!providerReady)
        {
            SetSafetyState(SafetyVisualState.Warning,
                $"Temperature provider unavailable — fan forced to 100% (0x{status.LastTemperatureProviderStatus:X8}).");
        }
        else if (status.OverTemperatureOverride != 0)
        {
            SetSafetyState(SafetyVisualState.Danger,
                "OVER-TEMPERATURE override active — fan forced to 100%.");
        }
        else if (status.FailSafeActive != 0 && status.TemperatureValid == 0)
        {
            SetSafetyState(SafetyVisualState.Warning,
                $"Temperature fail-safe active — fan forced to 100% (failures: {status.ConsecutiveTemperatureFailures}).");
        }
        else if (status.FailSafeActive != 0)
        {
            SetSafetyState(SafetyVisualState.Warning,
                "Fail-safe active — fan forced to 100%.");
        }
        else
        {
            SetSafetyState(SafetyVisualState.Healthy,
                "Normal split-driver control active. Automatic temperature control continues without the GUI.");
        }
    }

    private void SetConnectionState(bool ready)
    {
        if (ready)
        {
            ConnectionBadgeText.Text = "Drivers ready";
            ConnectionBadge.Background = BrushFrom("#193C34");
            ConnectionBadge.BorderBrush = BrushFrom("#2F8C73");
            ConnectionIndicator.Fill = HealthyBrush;
        }
        else
        {
            ConnectionBadgeText.Text = "Driver unavailable";
            ConnectionBadge.Background = BrushFrom("#3A1820");
            ConnectionBadge.BorderBrush = BrushFrom("#8F3545");
            ConnectionIndicator.Fill = DangerBrush;
        }
    }

    private void SetSafetyState(SafetyVisualState state, string message)
    {
        SafetyText.Text = message;
        switch (state)
        {
            case SafetyVisualState.Healthy:
                SafetyBorder.Background = SafetyHealthyBackground;
                SafetyBorder.BorderBrush = SafetyHealthyBorder;
                SafetyIndicator.Fill = HealthyBrush;
                break;
            case SafetyVisualState.Warning:
                SafetyBorder.Background = SafetyWarningBackground;
                SafetyBorder.BorderBrush = SafetyWarningBorder;
                SafetyIndicator.Fill = WarningBrush;
                break;
            default:
                SafetyBorder.Background = SafetyDangerBackground;
                SafetyBorder.BorderBrush = SafetyDangerBorder;
                SafetyIndicator.Fill = DangerBrush;
                break;
        }
    }

    private void UpdateFanAnimation(uint percent, bool hardwareReady)
    {
        if (!hardwareReady)
        {
            StopFanAnimation();
            return;
        }

        percent = Math.Clamp(percent, 30u, 100u);
        FanImage.Opacity = 1.0;

        if (_fanAnimationRunning && _lastAnimatedPercent == percent)
        {
            return;
        }

        double normalized = (percent - 30u) / 70.0;
        double secondsPerTurn = 1.45 - (1.10 * normalized);
        double currentAngle = FanRotateTransform.Angle;

        var animation = new DoubleAnimation
        {
            From = currentAngle,
            To = currentAngle + 360.0,
            Duration = TimeSpan.FromSeconds(secondsPerTurn),
            RepeatBehavior = RepeatBehavior.Forever,
            FillBehavior = FillBehavior.HoldEnd
        };

        FanRotateTransform.BeginAnimation(
            RotateTransform.AngleProperty,
            animation,
            HandoffBehavior.SnapshotAndReplace);

        _lastAnimatedPercent = percent;
        _fanAnimationRunning = true;
    }

    private void StopFanAnimation()
    {
        FanRotateTransform.BeginAnimation(RotateTransform.AngleProperty, null);
        FanImage.Opacity = 0.38;
        _fanAnimationRunning = false;
        _lastAnimatedPercent = null;
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

    private enum SafetyVisualState
    {
        Healthy,
        Warning,
        Danger
    }
}
