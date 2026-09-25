param([Parameter(Mandatory=$true)][string]$Source, [Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$sourceImage = [System.Drawing.Bitmap]::new((Resolve-Path $Source).Path)
try {
    if ($sourceImage.Width -ne 128 -or $sourceImage.Height -ne 128) { throw 'Expected the supplied 128x128 fan PNG.' }
    $tinted = [System.Drawing.Bitmap]::new(128,128,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        for ($y=0; $y -lt 128; $y++) { for ($x=0; $x -lt 128; $x++) {
            $a = $sourceImage.GetPixel($x,$y).A
            $tinted.SetPixel($x,$y,[System.Drawing.Color]::FromArgb($a,93,228,199))
        }}
        $sizes = @(16,24,32,48,64,128,256)
        $images = [System.Collections.Generic.List[byte[]]]::new()
        foreach ($size in $sizes) {
            $bitmap = [System.Drawing.Bitmap]::new($size,$size,[System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
            $g = [System.Drawing.Graphics]::FromImage($bitmap)
            $brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255,15,23,36))
            $stream = [System.IO.MemoryStream]::new()
            try {
                $g.Clear([System.Drawing.Color]::Transparent)
                $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
                $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
                $g.FillEllipse($brush,[single]0,[single]0,[single]$size,[single]$size)
                $drawSize = [single]($size * 0.76)
                $rect = [System.Drawing.RectangleF]::new([single]($size/2-$drawSize*64.502/128),[single]($size/2-$drawSize*63.869/128),$drawSize,$drawSize)
                $g.DrawImage($tinted,$rect)
                $bitmap.Save($stream,[System.Drawing.Imaging.ImageFormat]::Png)
                $images.Add($stream.ToArray())
            } finally { $stream.Dispose(); $brush.Dispose(); $g.Dispose(); $bitmap.Dispose() }
        }
        $file = [System.IO.File]::Create($Destination)
        $writer = [System.IO.BinaryWriter]::new($file)
        try {
            $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$sizes.Count)
            $offset = [uint32](6+16*$sizes.Count)
            for ($i=0; $i -lt $sizes.Count; $i++) {
                $dimension = if ($sizes[$i] -eq 256) { 0 } else { $sizes[$i] }
                $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
                $writer.Write([byte]0); $writer.Write([byte]0)
                $writer.Write([uint16]1); $writer.Write([uint16]32)
                $writer.Write([uint32]$images[$i].Length); $writer.Write($offset)
                $offset += [uint32]$images[$i].Length
            }
            foreach ($image in $images) { $writer.Write([byte[]]$image) }
        } finally { $writer.Dispose(); $file.Dispose() }
    } finally { $tinted.Dispose() }
} finally { $sourceImage.Dispose() }
