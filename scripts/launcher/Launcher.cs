// manga-translate.exe for the portable release: runs the bundled python\pythonw.exe with
// "-m manga_translate" from the folder this launcher sits in, without a console window.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class Launcher
{
    [STAThread]
    static int Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(Path.Combine(root, "python"), "pythonw.exe");
        if (!File.Exists(pythonw))
        {
            MessageBox.Show(
                "python\\pythonw.exe 파일이 없습니다. 압축을 모두 풀었는지 확인하세요.\n" + pythonw,
                "manga-translate",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
        var start = new ProcessStartInfo(pythonw, "-m manga_translate");
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        Process.Start(start);
        return 0;
    }
}
