using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Windows.Forms;

namespace InventoryDesktopApp
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
                Application.ThreadException += delegate(object sender, System.Threading.ThreadExceptionEventArgs args)
                {
                    CrashReporter.Write(args.Exception);
                    MessageBox.Show(
                        "アプリでエラーが発生しました。\ncrash.log を確認してください。",
                        "起動エラー",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                };
                AppDomain.CurrentDomain.UnhandledException += delegate(object sender, UnhandledExceptionEventArgs args)
                {
                    var ex = args.ExceptionObject as Exception ?? new Exception("Unknown unhandled exception");
                    CrashReporter.Write(ex);
                };

                Application.Run(new MainForm());
            }
            catch (Exception ex)
            {
                CrashReporter.Write(ex);
                MessageBox.Show(
                    "起動に失敗しました。\ncrash.log を確認してください。",
                    "起動エラー",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }

    internal static class CrashReporter
    {
        public static void Write(Exception ex)
        {
            try
            {
                var path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "crash.log");
                var text = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                    + Environment.NewLine
                    + ex
                    + Environment.NewLine
                    + new string('-', 80)
                    + Environment.NewLine;
                File.AppendAllText(path, text, Encoding.UTF8);
            }
            catch
            {
            }
        }
    }

    [DataContract]
    internal class InventoryItemLine
    {
        [DataMember] public string LineId { get; set; }
        [DataMember] public string PartCode { get; set; }
        [DataMember] public string Size { get; set; }
        [DataMember] public int ThicknessMm { get; set; }
        [DataMember] public string FinishText { get; set; }
        [DataMember] public string Grade { get; set; }
        [DataMember] public int SheetCount { get; set; }

        public InventoryItemLine()
        {
            LineId = Guid.NewGuid().ToString("N");
            PartCode = "";
            Size = "";
            FinishText = "";
            Grade = "";
            SheetCount = 1;
        }

        public string Identifier
        {
            get
            {
                return string.Format("#{0}-{1}{2} {3} {4} {5}", PartCode, Size, ThicknessMm, FinishText, Grade, SheetCount);
            }
        }

        public int HeightMm
        {
            get { return ThicknessMm * SheetCount; }
        }
    }

    [DataContract]
    internal class PalletRecord
    {
        [DataMember] public string PalletNumber { get; set; }
        [DataMember] public string LocationCode { get; set; }
        [DataMember] public int StackOrder { get; set; }
        [DataMember] public List<InventoryItemLine> Items { get; set; }
        [DataMember] public DateTime UpdatedAt { get; set; }

        public PalletRecord()
        {
            PalletNumber = "";
            LocationCode = "";
            Items = new List<InventoryItemLine>();
            UpdatedAt = DateTime.Now;
        }

        public int TotalSheets { get { return Items.Sum(item => item.SheetCount); } }
        public int MaterialHeightMm { get { return Items.Sum(item => item.HeightMm); } }
        public int EstimatedHeightMm { get { return 200 + MaterialHeightMm; } }
        public string StackLabel { get { return (StackOrder + 1).ToString() + "段目"; } }
        public string SummaryText
        {
            get
            {
                if (Items.Count == 0) return "明細なし";
                var preview = Items.Take(2).Select(item => item.Identifier).ToArray();
                var text = string.Join(" / ", preview);
                return Items.Count > 2 ? text + " ..." : text;
            }
        }
    }

    [DataContract]
    internal class InventoryStore
    {
        [DataMember] public List<PalletRecord> Pallets { get; set; }
        [DataMember] public List<string> Locations { get; set; }

        public InventoryStore()
        {
            Pallets = new List<PalletRecord>();
            Locations = new List<string>();
        }
    }

    internal class PalletGridRow
    {
        public string PalletNumber { get; set; }
        public string LocationCode { get; set; }
        public string StackLabel { get; set; }
        public int ItemTypeCount { get; set; }
        public int TotalSheets { get; set; }
        public int EstimatedHeightMm { get; set; }
        public string SummaryText { get; set; }
        public DateTime UpdatedAt { get; set; }
    }

    internal class ItemGridRow
    {
        public string LineId { get; set; }
        public string Identifier { get; set; }
        public string PartCode { get; set; }
        public string Size { get; set; }
        public int ThicknessMm { get; set; }
        public string FinishText { get; set; }
        public string Grade { get; set; }
        public int SheetCount { get; set; }
        public int HeightMm { get; set; }
    }

    internal class InventorySummaryRow
    {
        public string Identifier { get; set; }
        public string PartCode { get; set; }
        public string Size { get; set; }
        public int ThicknessMm { get; set; }
        public string FinishText { get; set; }
        public string Grade { get; set; }
        public int TotalSheets { get; set; }
        public int TotalHeightMm { get; set; }
        public int PalletCount { get; set; }
        public string Locations { get; set; }
    }

    internal sealed class MainForm : Form
    {
        private readonly string dataFilePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "inventory-data.json");
        private readonly List<PalletRecord> pallets = new List<PalletRecord>();
        private readonly List<string> locations = new List<string>();
        private readonly BindingSource palletGridBinding = new BindingSource();
        private readonly BindingSource itemGridBinding = new BindingSource();
        private readonly BindingSource inventorySummaryBinding = new BindingSource();
        private readonly ToolTip warehouseToolTip = new ToolTip();

        private TextBox palletNumberTextBox;
        private ComboBox palletLocationComboBox;
        private TextBox newLocationTextBox;
        private TextBox searchTextBox;
        private TextBox partCodeTextBox;
        private ComboBox sizeComboBox;
        private NumericUpDown thicknessInput;
        private TextBox finishTextBox;
        private ComboBox gradeComboBox;
        private NumericUpDown sheetCountInput;
        private Label summaryLabel;
        private Label selectedPalletLabel;
        private Label itemPreviewLabel;
        private TableLayoutPanel rootLayout;
        private TableLayoutPanel editorLayout;
        private Control palletEditorCard;
        private Control itemEditorCard;
        private Panel warehouseBoard;
        private Panel isometricWarehouseBoard;
        private SplitContainer bottomSplit;
        private SplitContainer leftBottomSplit;
        private SplitContainer gridSplit;
        private DataGridView palletGrid;
        private DataGridView itemGrid;
        private DataGridView inventorySummaryGrid;
        private readonly Dictionary<string, Rectangle> locationMapRects = new Dictionary<string, Rectangle>();
        private readonly Dictionary<string, Rectangle> palletMapRects = new Dictionary<string, Rectangle>();
        private readonly Dictionary<string, Rectangle> isometricPalletRects = new Dictionary<string, Rectangle>();
        private string draggedPalletNumber;
        private Point dragCursorPoint;
        private Point dragOffset;
        private string hoveredPalletNumber;
        private string hoveredIsometricPalletNumber;

        public MainForm()
        {
            Text = "在庫管理デスクトップアプリ";
            StartPosition = FormStartPosition.CenterScreen;
            MinimumSize = new Size(1380, 860);
            Size = new Size(1540, 940);
            Font = new Font("Yu Gothic UI", 10F, FontStyle.Regular, GraphicsUnit.Point);
            BackColor = Color.FromArgb(243, 246, 249);

            BuildLayout();
            Resize += delegate { ApplyResponsiveLayout(); };
            warehouseToolTip.AutoPopDelay = 12000;
            warehouseToolTip.InitialDelay = 250;
            warehouseToolTip.ReshowDelay = 150;
            warehouseToolTip.ShowAlways = true;
            LoadInventory();
            EnsureSeedLocations();
            RefreshLocationComboBoxes();
            RefreshAllViews();
            ApplyResponsiveLayout();
        }

        private void BuildLayout()
        {
            rootLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 3,
                Padding = new Padding(18)
            };
            rootLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            rootLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 74F));
            rootLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 26F));
            Controls.Add(rootLayout);

            rootLayout.Controls.Add(BuildHeaderPanel(), 0, 0);
            rootLayout.Controls.Add(BuildWarehousePanel(), 0, 1);
            rootLayout.Controls.Add(BuildBottomArea(), 0, 2);
        }

        private Control BuildHeaderPanel()
        {
            var panel = CreateCardPanel();
            panel.Padding = new Padding(18, 16, 18, 14);
            panel.Margin = new Padding(0, 0, 0, 14);

            var title = new Label
            {
                Text = "Pallet Inventory Hub",
                Font = new Font("Yu Gothic UI Semibold", 18F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                Dock = DockStyle.Top,
                Height = 38
            };

            summaryLabel = new Label
            {
                Text = "パレット 0枚 / 明細 0件 / 総枚数 0 / ロケーション 0",
                Font = new Font("Yu Gothic UI", 10.5F, FontStyle.Regular, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(93, 109, 126),
                Dock = DockStyle.Top,
                Height = 30
            };

            panel.Controls.Add(summaryLabel);
            panel.Controls.Add(title);
            return panel;
        }

        private Control BuildEditorArea()
        {
            editorLayout = new TableLayoutPanel
            {
                Dock = DockStyle.Top,
                ColumnCount = 2,
                AutoSize = true,
                Margin = new Padding(0, 0, 0, 12)
            };
            editorLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 42F));
            editorLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 58F));

            palletEditorCard = BuildPalletEditorCard();
            itemEditorCard = BuildItemEditorCard();
            editorLayout.Controls.Add(palletEditorCard, 0, 0);
            editorLayout.Controls.Add(itemEditorCard, 1, 0);
            return editorLayout;
        }

        private Control BuildPalletEditorCard()
        {
            var card = CreateCardPanel();
            card.Margin = new Padding(0, 0, 8, 0);
            card.MinimumSize = new Size(0, 230);

            var layout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 6,
                Padding = new Padding(12)
            };

            palletNumberTextBox = new TextBox();
            palletLocationComboBox = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList };
            newLocationTextBox = new TextBox();

            var savePalletButton = CreatePrimaryButton("パレットを登録 / 更新");
            savePalletButton.Click += delegate { AddOrUpdatePallet(); };

            var addLocationButton = CreateSecondaryButton("ロケーション追加");
            addLocationButton.Click += delegate { AddLocation(); };

            layout.Controls.Add(CreateSectionTitle("パレット情報"), 0, 0);
            layout.Controls.Add(CreateLabeledField("パレット番号", palletNumberTextBox), 0, 1);
            layout.Controls.Add(CreateLabeledField("ロケーション", palletLocationComboBox), 0, 2);
            layout.Controls.Add(savePalletButton, 0, 3);
            layout.Controls.Add(CreateLabeledField("新しいロケーション名", newLocationTextBox), 0, 4);
            layout.Controls.Add(addLocationButton, 0, 5);

            card.Controls.Add(layout);
            return card;
        }

        private Control BuildItemEditorCard()
        {
            var card = CreateCardPanel();
            card.Margin = new Padding(0, 0, 0, 0);
            card.MinimumSize = new Size(0, 230);

            var grid = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 3,
                RowCount = 5,
                Padding = new Padding(12)
            };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33F));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33F));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33F));

            partCodeTextBox = new TextBox();
            sizeComboBox = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList };
            sizeComboBox.Items.AddRange(new object[] { "L", "LL", "EL", "OL" });
            if (sizeComboBox.Items.Count > 0) sizeComboBox.SelectedIndex = 1;

            thicknessInput = new NumericUpDown { Minimum = 1, Maximum = 999, Value = 10, ThousandsSeparator = true };
            finishTextBox = new TextBox();
            gradeComboBox = new ComboBox { DropDownStyle = ComboBoxStyle.DropDown };
            gradeComboBox.Items.AddRange(new object[] { "A", "B", "C", "K", "片A", "S" });
            gradeComboBox.Text = "A";
            sheetCountInput = new NumericUpDown { Minimum = 1, Maximum = 9999, Value = 80, ThousandsSeparator = true };

            itemPreviewLabel = new Label
            {
                Text = "#38-LL10 S/S A 80",
                AutoSize = true,
                ForeColor = Color.FromArgb(93, 109, 126),
                Margin = new Padding(6, 4, 6, 10)
            };

            partCodeTextBox.TextChanged += delegate { UpdateItemPreview(); };
            sizeComboBox.SelectedIndexChanged += delegate { UpdateItemPreview(); };
            thicknessInput.ValueChanged += delegate { UpdateItemPreview(); };
            finishTextBox.TextChanged += delegate { UpdateItemPreview(); };
            gradeComboBox.TextChanged += delegate { UpdateItemPreview(); };
            sheetCountInput.ValueChanged += delegate { UpdateItemPreview(); };

            var addItemButton = CreatePrimaryButton("選択パレットへ明細追加 / 更新");
            addItemButton.Click += delegate { AddOrUpdateItemLine(); };

            var removeItemButton = CreateSecondaryButton("選択明細を削除");
            removeItemButton.Click += delegate { DeleteSelectedItemLine(); };

            var sectionTitle = CreateSectionTitle("パレット内の明細");
            grid.Controls.Add(sectionTitle, 0, 0);
            grid.SetColumnSpan(sectionTitle, 3);
            grid.Controls.Add(CreateLabeledField("品番 (#除く)", partCodeTextBox), 0, 1);
            grid.Controls.Add(CreateLabeledField("サイズ", sizeComboBox), 1, 1);
            grid.Controls.Add(CreateLabeledField("厚み(mm)", thicknessInput), 2, 1);
            grid.Controls.Add(CreateLabeledField("加工 / 裏表", finishTextBox), 0, 2);
            grid.Controls.Add(CreateLabeledField("グレード", gradeComboBox), 1, 2);
            grid.Controls.Add(CreateLabeledField("枚数", sheetCountInput), 2, 2);
            grid.Controls.Add(itemPreviewLabel, 0, 3);
            grid.SetColumnSpan(itemPreviewLabel, 3);
            grid.Controls.Add(addItemButton, 1, 4);
            grid.Controls.Add(removeItemButton, 2, 4);

            card.Controls.Add(grid);
            return card;
        }

        private Control BuildActionCard()
        {
            var card = CreateCardPanel();

            var layout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 7,
                Padding = new Padding(18)
            };

            searchTextBox = new TextBox();
            searchTextBox.TextChanged += delegate { RefreshAllViews(); };

            selectedPalletLabel = new Label
            {
                Text = "選択中パレット: なし",
                AutoSize = true,
                ForeColor = Color.FromArgb(34, 47, 62),
                Margin = new Padding(6, 0, 6, 8)
            };

            var clearButton = CreateSecondaryButton("入力をクリア");
            clearButton.Click += delegate { ClearInputs(); };

            var deletePalletButton = CreateSecondaryButton("選択パレットを削除");
            deletePalletButton.Click += delegate { DeleteSelectedPallet(); };

            var saveButton = CreatePrimaryButton("今すぐ保存");
            saveButton.Click += delegate
            {
                SaveInventory();
                MessageBox.Show("在庫データを保存しました。", "保存完了", MessageBoxButtons.OK, MessageBoxIcon.Information);
            };

            layout.Controls.Add(CreateSectionTitle("操作"), 0, 0);
            layout.Controls.Add(CreateLabeledField("検索", searchTextBox), 0, 1);
            layout.Controls.Add(selectedPalletLabel, 0, 2);
            layout.Controls.Add(new Label
            {
                Text = "識別例: #38-LL10 S/S A 80",
                AutoSize = true,
                ForeColor = Color.FromArgb(93, 109, 126),
                Margin = new Padding(6, 0, 6, 8)
            }, 0, 3);
            layout.Controls.Add(deletePalletButton, 0, 4);
            layout.Controls.Add(clearButton, 0, 5);
            layout.Controls.Add(saveButton, 0, 6);

            card.Controls.Add(layout);
            return card;
        }

        private Control BuildWarehousePanel()
        {
            var card = CreateCardPanel();
            card.Margin = new Padding(0, 0, 0, 14);
            card.Padding = new Padding(0);
            card.BackColor = Color.FromArgb(8, 19, 36);

            var shell = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 3,
                BackColor = Color.FromArgb(8, 19, 36)
            };
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));

            shell.Controls.Add(BuildMapHeaderBar(), 0, 0);
            shell.Controls.Add(BuildMapToolbar(), 0, 1);

            var viewTabs = new TabControl
            {
                Dock = DockStyle.Fill,
                Padding = new Point(14, 6)
            };

            var topTab = new TabPage("上面図");
            topTab.BackColor = Color.FromArgb(8, 19, 36);
            warehouseBoard = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(8, 19, 36)
            };
            warehouseBoard.Paint += WarehouseBoard_Paint;
            warehouseBoard.MouseDown += WarehouseBoard_MouseDown;
            warehouseBoard.MouseMove += WarehouseBoard_MouseMove;
            warehouseBoard.MouseUp += WarehouseBoard_MouseUp;
            warehouseBoard.Resize += delegate { warehouseBoard.Invalidate(); };
            topTab.Controls.Add(warehouseBoard);

            var isoTab = new TabPage("45度ビュー");
            isoTab.BackColor = Color.FromArgb(8, 19, 36);
            isometricWarehouseBoard = new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.FromArgb(8, 19, 36)
            };
            isometricWarehouseBoard.Paint += IsometricWarehouseBoard_Paint;
            isometricWarehouseBoard.MouseMove += IsometricWarehouseBoard_MouseMove;
            isometricWarehouseBoard.Resize += delegate { isometricWarehouseBoard.Invalidate(); };
            isoTab.Controls.Add(isometricWarehouseBoard);

            var inventoryTab = new TabPage("在庫一覧");
            inventoryTab.BackColor = Color.FromArgb(243, 246, 249);
            inventoryTab.Controls.Add(BuildInventorySummaryPanel());

            viewTabs.TabPages.Add(topTab);
            viewTabs.TabPages.Add(isoTab);
            viewTabs.TabPages.Add(inventoryTab);

            shell.Controls.Add(viewTabs, 0, 2);
            card.Controls.Add(shell);
            return card;
        }

        private Control BuildGridArea()
        {
            gridSplit = new SplitContainer
            {
                Dock = DockStyle.Top,
                FixedPanel = FixedPanel.None,
                Height = 320,
                BackColor = Color.FromArgb(220, 226, 234)
            };

            gridSplit.Panel1.Controls.Add(BuildPalletGridPanel());
            gridSplit.Panel2.Controls.Add(BuildItemGridPanel());
            return gridSplit;
        }

        private Control BuildInventorySummaryPanel()
        {
            var card = CreateCardPanel();
            card.Dock = DockStyle.Fill;
            card.Padding = new Padding(14);

            var shell = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 2
            };
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            shell.Controls.Add(CreateSectionTitle("在庫一覧"), 0, 0);

            inventorySummaryGrid = new DataGridView
            {
                Dock = DockStyle.Fill,
                AutoGenerateColumns = false,
                AllowUserToAddRows = false,
                ReadOnly = true,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                MultiSelect = false,
                RowHeadersVisible = false,
                BackgroundColor = Color.White,
                BorderStyle = BorderStyle.None,
                GridColor = Color.FromArgb(229, 232, 236)
            };

            inventorySummaryGrid.Columns.Add(CreateTextColumn("Identifier", "識別", 240));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("PartCode", "品番", 70));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("Size", "サイズ", 70));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("ThicknessMm", "厚み", 65));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("FinishText", "加工 / 裏表", 110));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("Grade", "グレード", 70));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("TotalSheets", "総枚数", 75));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("TotalHeightMm", "総高さ", 75));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("PalletCount", "パレット数", 85));
            inventorySummaryGrid.Columns.Add(CreateTextColumn("Locations", "保管場所", 180));
            inventorySummaryGrid.DataSource = inventorySummaryBinding;

            shell.Controls.Add(inventorySummaryGrid, 0, 1);
            card.Controls.Add(shell);
            return card;
        }

        private Control BuildBottomArea()
        {
            bottomSplit = new SplitContainer
            {
                Dock = DockStyle.Fill,
                FixedPanel = FixedPanel.None,
                BackColor = Color.FromArgb(220, 226, 234)
            };

            leftBottomSplit = new SplitContainer
            {
                Dock = DockStyle.Fill,
                Orientation = Orientation.Horizontal,
                FixedPanel = FixedPanel.None,
                BackColor = Color.FromArgb(220, 226, 234)
            };

            var editorScroll = new Panel
            {
                Dock = DockStyle.Fill,
                AutoScroll = true,
                Padding = new Padding(0, 0, 6, 0)
            };
            editorScroll.Controls.Add(BuildEditorArea());

            var actionScroll = new Panel
            {
                Dock = DockStyle.Fill,
                AutoScroll = true,
                Padding = new Padding(0, 0, 6, 0)
            };
            actionScroll.Controls.Add(BuildActionCardModern());

            var gridScroll = new Panel
            {
                Dock = DockStyle.Fill,
                AutoScroll = true,
                Padding = new Padding(6, 0, 0, 0)
            };
            gridScroll.Controls.Add(BuildGridArea());

            leftBottomSplit.Panel1.Controls.Add(editorScroll);
            leftBottomSplit.Panel2.Controls.Add(actionScroll);
            bottomSplit.Panel1.Controls.Add(leftBottomSplit);
            bottomSplit.Panel2.Controls.Add(gridScroll);
            return bottomSplit;
        }

        private Control BuildActionCardModern()
        {
            var card = CreateCardPanel();

            var layout = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 10,
                Padding = new Padding(18)
            };

            if (searchTextBox == null)
            {
                searchTextBox = new TextBox();
                searchTextBox.TextChanged += delegate { RefreshAllViews(); };
            }

            if (selectedPalletLabel == null)
            {
                selectedPalletLabel = new Label();
            }

            selectedPalletLabel.Text = "選択中パレット: なし";
            selectedPalletLabel.AutoSize = true;
            selectedPalletLabel.ForeColor = Color.FromArgb(34, 47, 62);
            selectedPalletLabel.Margin = new Padding(6, 0, 6, 8);

            var clearButton = CreateSecondaryButton("入力をクリア");
            clearButton.Click += delegate { ClearInputs(); };

            var deletePalletButton = CreateSecondaryButton("選択パレットを削除");
            deletePalletButton.Click += delegate { DeleteSelectedPallet(); };

            var saveButton = CreatePrimaryButton("端末に保存");
            saveButton.Click += delegate
            {
                SaveInventory();
                MessageBox.Show("端末内の在庫データを保存しました。", "保存完了", MessageBoxButtons.OK, MessageBoxIcon.Information);
            };

            var exportButton = CreateSecondaryButton("Export");
            exportButton.Click += delegate { ExportInventoryData(); };

            var importButton = CreateSecondaryButton("Import");
            importButton.Click += delegate { ImportInventoryData(); };

            layout.Controls.Add(CreateSectionTitle("操作"), 0, 0);
            layout.Controls.Add(CreateLabeledField("検索", searchTextBox), 0, 1);
            layout.Controls.Add(selectedPalletLabel, 0, 2);
            layout.Controls.Add(new Label
            {
                Text = "識別例: #38-LL10 S/S A 80",
                AutoSize = true,
                ForeColor = Color.FromArgb(93, 109, 126),
                Margin = new Padding(6, 0, 6, 8)
            }, 0, 3);
            layout.Controls.Add(deletePalletButton, 0, 4);
            layout.Controls.Add(clearButton, 0, 5);
            layout.Controls.Add(saveButton, 0, 6);
            layout.Controls.Add(exportButton, 0, 7);
            layout.Controls.Add(importButton, 0, 8);
            layout.Controls.Add(new Label
            {
                Text = "オフライン運用 / 共有時のみ Export",
                AutoSize = true,
                ForeColor = Color.FromArgb(93, 109, 126),
                Margin = new Padding(6, 6, 6, 0)
            }, 0, 9);

            card.Controls.Add(layout);
            return card;
        }

        private void ApplyResponsiveLayout()
        {
            if (rootLayout == null || bottomSplit == null || leftBottomSplit == null || gridSplit == null || editorLayout == null)
            {
                return;
            }

            var width = ClientSize.Width;
            var compact = width < 1280;
            var medium = width < 1550;

            rootLayout.SuspendLayout();
            editorLayout.SuspendLayout();

            rootLayout.RowStyles[1].Height = compact ? 64F : 74F;
            rootLayout.RowStyles[2].Height = compact ? 36F : 26F;

            bottomSplit.Panel1MinSize = compact ? 180 : 220;
            bottomSplit.Panel2MinSize = compact ? 220 : 260;
            bottomSplit.Orientation = compact ? Orientation.Horizontal : Orientation.Vertical;
            SetSafeSplitterDistance(
                bottomSplit,
                compact
                    ? Math.Max(220, bottomSplit.Height / 2)
                    : Math.Max(300, Math.Min(bottomSplit.Width - 260, 380)));

            leftBottomSplit.Panel1MinSize = compact ? 160 : 180;
            leftBottomSplit.Panel2MinSize = compact ? 140 : 160;
            leftBottomSplit.Orientation = compact ? Orientation.Vertical : Orientation.Horizontal;
            SetSafeSplitterDistance(
                leftBottomSplit,
                compact
                    ? Math.Max(180, leftBottomSplit.Width / 2)
                    : Math.Max(220, leftBottomSplit.Height / 2));

            gridSplit.Orientation = compact ? Orientation.Horizontal : Orientation.Vertical;
            gridSplit.Dock = compact ? DockStyle.Fill : DockStyle.Top;
            gridSplit.Height = compact ? 520 : 320;
            gridSplit.Panel1MinSize = compact ? 180 : 320;
            gridSplit.Panel2MinSize = compact ? 180 : 300;
            SetSafeSplitterDistance(
                gridSplit,
                compact
                    ? Math.Max(180, gridSplit.Height / 2)
                    : Math.Max(300, Math.Min(gridSplit.Width - 300, 520)));

            editorLayout.ColumnStyles.Clear();
            editorLayout.RowStyles.Clear();
            editorLayout.Controls.Clear();

            if (medium)
            {
                editorLayout.ColumnCount = 1;
                editorLayout.RowCount = 2;
                editorLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
                editorLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                editorLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                if (palletEditorCard != null) editorLayout.Controls.Add(palletEditorCard, 0, 0);
                if (itemEditorCard != null) editorLayout.Controls.Add(itemEditorCard, 0, 1);
            }
            else
            {
                editorLayout.ColumnCount = 2;
                editorLayout.RowCount = 1;
                editorLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 36F));
                editorLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 64F));
                editorLayout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
                if (palletEditorCard != null) editorLayout.Controls.Add(palletEditorCard, 0, 0);
                if (itemEditorCard != null) editorLayout.Controls.Add(itemEditorCard, 1, 0);
            }

            editorLayout.ResumeLayout();
            rootLayout.ResumeLayout();
        }

        private void SetSafeSplitterDistance(SplitContainer splitContainer, int desiredDistance)
        {
            var total = splitContainer.Orientation == Orientation.Vertical
                ? splitContainer.ClientSize.Width
                : splitContainer.ClientSize.Height;

            if (total <= 0)
            {
                return;
            }

            var min = splitContainer.Panel1MinSize;
            var max = total - splitContainer.Panel2MinSize - splitContainer.SplitterWidth;
            if (max < min)
            {
                max = min;
            }

            var safe = Math.Max(min, Math.Min(max, desiredDistance));
            if (safe >= 0)
            {
                splitContainer.SplitterDistance = safe;
            }
        }

        private Control BuildPalletGridPanel()
        {
            var card = CreateCardPanel();
            card.Margin = new Padding(0, 0, 12, 0);
            card.Padding = new Padding(14);

            var shell = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 2
            };
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            shell.Controls.Add(CreateSectionTitle("パレット一覧"), 0, 0);

            palletGrid = new DataGridView
            {
                Dock = DockStyle.Fill,
                AutoGenerateColumns = false,
                AllowUserToAddRows = false,
                ReadOnly = true,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                MultiSelect = false,
                RowHeadersVisible = false,
                BackgroundColor = Color.White,
                BorderStyle = BorderStyle.None,
                GridColor = Color.FromArgb(229, 232, 236)
            };
            palletGrid.SelectionChanged += delegate { OnPalletSelectionChanged(); };

            palletGrid.Columns.Add(CreateTextColumn("PalletNumber", "パレット番号", 130));
            palletGrid.Columns.Add(CreateTextColumn("LocationCode", "ロケーション", 100));
            palletGrid.Columns.Add(CreateTextColumn("StackLabel", "積み位置", 80));
            palletGrid.Columns.Add(CreateTextColumn("ItemTypeCount", "種類数", 70));
            palletGrid.Columns.Add(CreateTextColumn("TotalSheets", "総枚数", 80));
            palletGrid.Columns.Add(CreateTextColumn("EstimatedHeightMm", "概算高(mm)", 95));
            palletGrid.Columns.Add(CreateTextColumn("SummaryText", "内容", 300));
            palletGrid.DataSource = palletGridBinding;

            shell.Controls.Add(palletGrid, 0, 1);
            card.Controls.Add(shell);
            return card;
        }

        private Control BuildMapHeaderBar()
        {
            var panel = new Panel
            {
                Dock = DockStyle.Top,
                Height = 42,
                Padding = new Padding(14, 10, 14, 6),
                BackColor = Color.FromArgb(6, 16, 30)
            };

            var title = new Label
            {
                Dock = DockStyle.Left,
                Width = 220,
                Text = "WAREHOUSE MAP",
                Font = new Font("Consolas", 15F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(92, 185, 255)
            };

            var status = new Label
            {
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleRight,
                Font = new Font("Yu Gothic UI", 9F, FontStyle.Regular, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(109, 130, 157),
                Text = "ドラッグで移動 / ホバーで明細"
            };

            panel.Controls.Add(status);
            panel.Controls.Add(title);
            return panel;
        }

        private Control BuildMapToolbar()
        {
            var panel = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                Height = 42,
                AutoSize = false,
                Padding = new Padding(12, 4, 12, 6),
                BackColor = Color.FromArgb(8, 19, 36)
            };

            panel.Controls.Add(CreateMapChip("真上", Color.FromArgb(22, 54, 96), Color.FromArgb(92, 185, 255)));
            panel.Controls.Add(CreateMapChip("左下45°", Color.FromArgb(17, 35, 66), Color.FromArgb(145, 168, 198)));
            panel.Controls.Add(CreateMapChip("右下45°", Color.FromArgb(17, 35, 66), Color.FromArgb(145, 168, 198)));
            panel.Controls.Add(CreateMapChip("L", Color.FromArgb(13, 88, 63), Color.FromArgb(175, 248, 217)));
            panel.Controls.Add(CreateMapChip("LL/EL", Color.FromArgb(17, 78, 116), Color.FromArgb(167, 224, 255)));
            panel.Controls.Add(CreateMapChip("OL", Color.FromArgb(104, 43, 54), Color.FromArgb(255, 210, 214)));
            panel.Controls.Add(CreateMapChip("MIX", Color.FromArgb(108, 82, 25), Color.FromArgb(255, 232, 171)));

            return panel;
        }

        private Control CreateMapChip(string text, Color backColor, Color foreColor)
        {
            return new Label
            {
                AutoSize = true,
                Text = "  " + text + "  ",
                Height = 24,
                Margin = new Padding(0, 0, 8, 0),
                Padding = new Padding(8, 4, 8, 4),
                BackColor = backColor,
                ForeColor = foreColor,
                Font = new Font("Yu Gothic UI", 8.8F, FontStyle.Bold, GraphicsUnit.Point)
            };
        }

        private Control BuildItemGridPanel()
        {
            var card = CreateCardPanel();
            card.Padding = new Padding(14);

            var shell = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 2
            };
            shell.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100F));
            shell.Controls.Add(CreateSectionTitle("選択パレットの明細"), 0, 0);

            itemGrid = new DataGridView
            {
                Dock = DockStyle.Fill,
                AutoGenerateColumns = false,
                AllowUserToAddRows = false,
                ReadOnly = true,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                MultiSelect = false,
                RowHeadersVisible = false,
                BackgroundColor = Color.White,
                BorderStyle = BorderStyle.None,
                GridColor = Color.FromArgb(229, 232, 236)
            };
            itemGrid.SelectionChanged += delegate { PopulateItemInputsFromSelection(); };

            itemGrid.Columns.Add(CreateTextColumn("Identifier", "識別", 240));
            itemGrid.Columns.Add(CreateTextColumn("PartCode", "品番", 70));
            itemGrid.Columns.Add(CreateTextColumn("Size", "サイズ", 70));
            itemGrid.Columns.Add(CreateTextColumn("ThicknessMm", "厚み", 65));
            itemGrid.Columns.Add(CreateTextColumn("FinishText", "加工 / 裏表", 110));
            itemGrid.Columns.Add(CreateTextColumn("Grade", "グレード", 70));
            itemGrid.Columns.Add(CreateTextColumn("SheetCount", "枚数", 65));
            itemGrid.Columns.Add(CreateTextColumn("HeightMm", "高さ(mm)", 80));
            itemGrid.DataSource = itemGridBinding;

            shell.Controls.Add(itemGrid, 0, 1);
            card.Controls.Add(shell);
            return card;
        }

        private void EnsureSeedLocations()
        {
            if (locations.Count > 0)
            {
                return;
            }

            locations.AddRange(new[] { "A-01", "A-02", "B-01", "B-02", "STAGE-1", "STAGE-2" });
        }

        private void RefreshLocationComboBoxes()
        {
            RefreshComboBoxItems(palletLocationComboBox, locations);
        }

        private void RefreshComboBoxItems(ComboBox comboBox, IEnumerable<string> values)
        {
            var selected = comboBox.SelectedItem as string;
            comboBox.Items.Clear();

            foreach (var value in values.OrderBy(item => item))
            {
                comboBox.Items.Add(value);
            }

            if (comboBox.Items.Count == 0)
            {
                return;
            }

            if (selected != null && comboBox.Items.Contains(selected))
            {
                comboBox.SelectedItem = selected;
            }
            else
            {
                comboBox.SelectedIndex = 0;
            }
        }

        private void AddLocation()
        {
            var location = (newLocationTextBox.Text ?? "").Trim();
            if (location.Length == 0)
            {
                MessageBox.Show("ロケーション名を入力してください。", "入力エラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (locations.Any(item => item.Equals(location, StringComparison.OrdinalIgnoreCase)))
            {
                MessageBox.Show("同じロケーションがすでに存在します。", "重複", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            locations.Add(location);
            newLocationTextBox.Text = "";
            RefreshLocationComboBoxes();
            RefreshWarehouseBoard();
            SaveInventory();
        }

        private void AddOrUpdatePallet()
        {
            var palletNumber = NormalizePalletNumber(palletNumberTextBox.Text);
            var location = palletLocationComboBox.SelectedItem as string;

            if (palletNumber.Length == 0 || location == null)
            {
                MessageBox.Show("パレット番号とロケーションは必須です。", "入力エラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var pallet = pallets.FirstOrDefault(item => item.PalletNumber.Equals(palletNumber, StringComparison.OrdinalIgnoreCase));
            if (pallet == null)
            {
                pallet = new PalletRecord
                {
                    PalletNumber = palletNumber,
                    LocationCode = location,
                    StackOrder = NextStackOrder(location),
                    UpdatedAt = DateTime.Now
                };
                pallets.Add(pallet);
            }
            else
            {
                var locationChanged = !pallet.LocationCode.Equals(location, StringComparison.OrdinalIgnoreCase);
                pallet.LocationCode = location;
                pallet.UpdatedAt = DateTime.Now;
                if (locationChanged)
                {
                    pallet.StackOrder = NextStackOrder(location, pallet.PalletNumber);
                    NormalizeStacks();
                }
            }

            SaveInventory();
            RefreshAllViews();
            SelectPalletInGrid(pallet.PalletNumber);
        }

        private void AddOrUpdateItemLine()
        {
            var pallet = GetSelectedPallet();
            if (pallet == null)
            {
                MessageBox.Show("先にパレットを選択または登録してください。", "パレット未選択", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            var partCode = NormalizePartCode(partCodeTextBox.Text);
            var size = (sizeComboBox.Text ?? "").Trim().ToUpperInvariant();
            var finish = (finishTextBox.Text ?? "").Trim();
            var grade = (gradeComboBox.Text ?? "").Trim();

            if (partCode.Length < 2 || partCode.Length > 3)
            {
                MessageBox.Show("品番は 2〜3 文字の英数字で入力してください。", "入力エラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            if (size.Length == 0 || finish.Length == 0 || grade.Length == 0)
            {
                MessageBox.Show("サイズ・加工 / 裏表・グレードは必須です。", "入力エラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var selectedLine = GetSelectedItemLine();
            if (selectedLine == null)
            {
                pallet.Items.Add(new InventoryItemLine
                {
                    PartCode = partCode,
                    Size = size,
                    ThicknessMm = (int)thicknessInput.Value,
                    FinishText = finish,
                    Grade = grade,
                    SheetCount = (int)sheetCountInput.Value
                });
            }
            else
            {
                selectedLine.PartCode = partCode;
                selectedLine.Size = size;
                selectedLine.ThicknessMm = (int)thicknessInput.Value;
                selectedLine.FinishText = finish;
                selectedLine.Grade = grade;
                selectedLine.SheetCount = (int)sheetCountInput.Value;
            }

            pallet.UpdatedAt = DateTime.Now;
            SaveInventory();
            RefreshAllViews();
            SelectPalletInGrid(pallet.PalletNumber);
            RefreshItemGridForSelectedPallet();
        }

        private void DeleteSelectedPallet()
        {
            var pallet = GetSelectedPallet();
            if (pallet == null)
            {
                MessageBox.Show("削除するパレットを選択してください。", "未選択", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            if (MessageBox.Show(pallet.PalletNumber + " を削除しますか？", "削除確認", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                return;
            }

            pallets.Remove(pallet);
            NormalizeStacks();
            SaveInventory();
            RefreshAllViews();
            ClearInputs();
        }

        private void DeleteSelectedItemLine()
        {
            var pallet = GetSelectedPallet();
            var line = GetSelectedItemLine();

            if (pallet == null || line == null)
            {
                MessageBox.Show("削除する明細を選択してください。", "未選択", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            pallet.Items.Remove(line);
            pallet.UpdatedAt = DateTime.Now;
            SaveInventory();
            RefreshAllViews();
            SelectPalletInGrid(pallet.PalletNumber);
            ClearItemInputs();
        }

        private void OnPalletSelectionChanged()
        {
            var pallet = GetSelectedPallet();
            if (pallet == null)
            {
                selectedPalletLabel.Text = "選択中パレット: なし";
                itemGridBinding.DataSource = new List<ItemGridRow>();
                return;
            }

            palletNumberTextBox.Text = pallet.PalletNumber;
            if (palletLocationComboBox.Items.Contains(pallet.LocationCode))
            {
                palletLocationComboBox.SelectedItem = pallet.LocationCode;
            }

            selectedPalletLabel.Text = string.Format(
                "選択中パレット: {0} / {1} / 種類 {2} / 概算高 {3}mm",
                pallet.PalletNumber,
                pallet.LocationCode,
                pallet.Items.Count,
                pallet.EstimatedHeightMm);

            RefreshItemGridForSelectedPallet();
        }

        private void RefreshItemGridForSelectedPallet()
        {
            var pallet = GetSelectedPallet();
            if (pallet == null)
            {
                itemGridBinding.DataSource = new List<ItemGridRow>();
                return;
            }

            itemGridBinding.DataSource = pallet.Items
                .Select(item => new ItemGridRow
                {
                    LineId = item.LineId,
                    Identifier = item.Identifier,
                    PartCode = item.PartCode,
                    Size = item.Size,
                    ThicknessMm = item.ThicknessMm,
                    FinishText = item.FinishText,
                    Grade = item.Grade,
                    SheetCount = item.SheetCount,
                    HeightMm = item.HeightMm
                })
                .OrderBy(item => item.PartCode)
                .ThenBy(item => item.Size)
                .ThenBy(item => item.ThicknessMm)
                .ToList();
        }

        private void PopulateItemInputsFromSelection()
        {
            var line = GetSelectedItemLine();
            if (line == null)
            {
                UpdateItemPreview();
                return;
            }

            partCodeTextBox.Text = line.PartCode;
            sizeComboBox.Text = line.Size;
            thicknessInput.Value = line.ThicknessMm;
            finishTextBox.Text = line.FinishText;
            gradeComboBox.Text = line.Grade;
            sheetCountInput.Value = line.SheetCount;
            UpdateItemPreview();
        }

        private void UpdateItemPreview()
        {
            var partCode = NormalizePartCode(partCodeTextBox.Text);
            var size = (sizeComboBox.Text ?? "").Trim().ToUpperInvariant();
            var finish = (finishTextBox.Text ?? "").Trim();
            var grade = (gradeComboBox.Text ?? "").Trim();

            if (partCode.Length == 0) partCode = "38";
            if (size.Length == 0) size = "LL";
            if (finish.Length == 0) finish = "S/S";
            if (grade.Length == 0) grade = "A";

            itemPreviewLabel.Text = string.Format(
                "#{0}-{1}{2} {3} {4} {5}  高さ目安 {6}mm",
                partCode,
                size,
                (int)thicknessInput.Value,
                finish,
                grade,
                (int)sheetCountInput.Value,
                (int)thicknessInput.Value * (int)sheetCountInput.Value);
        }

        private PalletRecord GetSelectedPallet()
        {
            if (palletGrid.CurrentRow == null)
            {
                return null;
            }

            var row = palletGrid.CurrentRow.DataBoundItem as PalletGridRow;
            if (row == null)
            {
                return null;
            }

            return pallets.FirstOrDefault(item => item.PalletNumber == row.PalletNumber);
        }

        private InventoryItemLine GetSelectedItemLine()
        {
            var pallet = GetSelectedPallet();
            if (pallet == null || itemGrid.CurrentRow == null)
            {
                return null;
            }

            var row = itemGrid.CurrentRow.DataBoundItem as ItemGridRow;
            if (row == null)
            {
                return null;
            }

            return pallet.Items.FirstOrDefault(item => item.LineId == row.LineId);
        }

        private void RefreshAllViews()
        {
            NormalizeStacks();
            RefreshSummary();
            RefreshWarehouseBoard();
            RefreshIsometricWarehouseBoard();
            RefreshPalletGrid();
            RefreshItemGridForSelectedPallet();
            RefreshInventorySummaryGrid();
            UpdateItemPreview();
        }

        private void RefreshSummary()
        {
            summaryLabel.Text = string.Format(
                "パレット {0}枚 / 明細 {1}件 / 総枚数 {2} / ロケーション {3} / 最大高さ {4}mm",
                pallets.Count,
                pallets.Sum(item => item.Items.Count),
                pallets.Sum(item => item.TotalSheets),
                locations.Count,
                pallets.Select(item => item.EstimatedHeightMm).DefaultIfEmpty(0).Max());
        }

        private void RefreshWarehouseBoard()
        {
            locationMapRects.Clear();
            palletMapRects.Clear();
            if (warehouseBoard != null)
            {
                warehouseBoard.Invalidate();
            }
        }

        private void RefreshIsometricWarehouseBoard()
        {
            isometricPalletRects.Clear();

            var orderedLocations = locations.OrderBy(item => item).ToList();
            if (orderedLocations.Count == 0)
            {
                orderedLocations.Add("未設定");
            }

            if (isometricWarehouseBoard != null)
            {
                isometricWarehouseBoard.Invalidate();
            }
        }

        private void WarehouseBoard_Paint(object sender, PaintEventArgs e)
        {
            var graphics = e.Graphics;
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            graphics.Clear(Color.FromArgb(8, 19, 36));

            locationMapRects.Clear();
            palletMapRects.Clear();

            var mapBounds = new Rectangle(18, 18, Math.Max(200, warehouseBoard.ClientSize.Width - 36), Math.Max(200, warehouseBoard.ClientSize.Height - 36));
            using (var outerPen = new Pen(Color.FromArgb(25, 113, 194)))
            {
                graphics.DrawRectangle(outerPen, mapBounds);
            }

            DrawGridBackground(graphics, mapBounds);

            var locationsByRow = GetLocationRows();
            for (var rowIndex = 0; rowIndex < locationsByRow.Count; rowIndex++)
            {
                var row = locationsByRow[rowIndex];
                for (var colIndex = 0; colIndex < row.Count; colIndex++)
                {
                    var rect = GetCellRectangle(mapBounds, rowIndex, colIndex, locationsByRow.Count, row.Count);
                    locationMapRects[row[colIndex]] = rect;
                    DrawLocationLabel(graphics, row[colIndex], rect, rowIndex, colIndex);
                }
            }

            foreach (var pallet in FilteredPallets().OrderBy(item => item.StackOrder))
            {
                if (!locationMapRects.ContainsKey(pallet.LocationCode))
                {
                    continue;
                }

                var cellRect = locationMapRects[pallet.LocationCode];
                var palletRect = GetPalletTopRectangle(pallet, cellRect);
                if (draggedPalletNumber == pallet.PalletNumber)
                {
                    palletRect = new Rectangle(
                        dragCursorPoint.X - dragOffset.X,
                        dragCursorPoint.Y - dragOffset.Y,
                        palletRect.Width,
                        palletRect.Height);
                }

                palletMapRects[pallet.PalletNumber] = palletRect;
                DrawTopPallet(graphics, pallet, palletRect, pallet.PalletNumber == hoveredPalletNumber || pallet.PalletNumber == draggedPalletNumber);
            }
        }

        private void IsometricWarehouseBoard_Paint(object sender, PaintEventArgs e)
        {
            var graphics = e.Graphics;
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            graphics.Clear(Color.FromArgb(7, 17, 32));
            isometricPalletRects.Clear();

            var bounds = new Rectangle(24, 24, Math.Max(320, isometricWarehouseBoard.ClientSize.Width - 48), Math.Max(240, isometricWarehouseBoard.ClientSize.Height - 48));
            DrawIsometricFloor(graphics, bounds);

            var orderedLocations = locations.OrderBy(ParseLocationSortKey).ThenBy(item => item).ToList();
            if (orderedLocations.Count == 0)
            {
                return;
            }

            var locationPoints = new Dictionary<string, PointF>();
            var cols = Math.Max(3, orderedLocations.Count);
            var originX = bounds.Left + bounds.Width * 0.50f;
            var originY = bounds.Top + bounds.Height * 0.56f;
            var stepX = Math.Min(112f, bounds.Width / (cols + 2f));
            var stepY = Math.Min(56f, bounds.Height / 8f);

            for (var i = 0; i < orderedLocations.Count; i++)
            {
                var row = i / 4;
                var col = i % 4;
                var isoX = originX + (col - row) * stepX;
                var isoY = originY + (col + row) * stepY * 0.55f;
                locationPoints[orderedLocations[i]] = new PointF(isoX, isoY);
            }

            foreach (var pair in locationPoints)
            {
                DrawIsometricLocationLabel(graphics, pair.Key, pair.Value);
            }

            foreach (var pallet in FilteredPallets().OrderBy(item => item.LocationCode).ThenBy(item => item.StackOrder))
            {
                PointF basePoint;
                if (!locationPoints.TryGetValue(pallet.LocationCode, out basePoint))
                {
                    continue;
                }

                var stackOffsetX = pallet.StackOrder * 14f;
                var stackOffsetY = -pallet.StackOrder * 8f;
                var boxRect = DrawIsometricMapPallet(
                    graphics,
                    pallet,
                    new PointF(basePoint.X + stackOffsetX, basePoint.Y + stackOffsetY),
                    pallet.PalletNumber == hoveredIsometricPalletNumber);
                isometricPalletRects[pallet.PalletNumber] = boxRect;
            }

            using (var infoBrush = new SolidBrush(Color.FromArgb(82, 129, 185)))
            using (var infoFont = new Font("Yu Gothic UI", 8.5F, FontStyle.Regular, GraphicsUnit.Point))
            {
                graphics.DrawString("45度ビュー: 位置関係と積み高さの確認用", infoFont, infoBrush, bounds.Left + 4, bounds.Top + 4);
            }
        }

        private void DrawIsometricFloor(Graphics graphics, Rectangle bounds)
        {
            var centerX = bounds.Left + bounds.Width * 0.50f;
            var centerY = bounds.Top + bounds.Height * 0.56f;
            var halfW = bounds.Width * 0.30f;
            var halfH = bounds.Height * 0.24f;

            var diamond = new[]
            {
                new PointF(centerX, centerY - halfH),
                new PointF(centerX + halfW, centerY),
                new PointF(centerX, centerY + halfH),
                new PointF(centerX - halfW, centerY)
            };

            using (var outlinePen = new Pen(Color.FromArgb(30, 98, 168), 2f))
            using (var gridPen = new Pen(Color.FromArgb(20, 58, 105), 1.2f))
            {
                graphics.DrawPolygon(outlinePen, diamond);
                graphics.DrawLine(outlinePen, centerX, centerY - halfH, centerX, centerY + halfH);
                graphics.DrawLine(outlinePen, centerX - halfW, centerY, centerX + halfW, centerY);

                for (var i = 1; i <= 3; i++)
                {
                    var t = i / 4f;
                    graphics.DrawLine(gridPen, centerX - halfW * (1 - t), centerY - halfH * t, centerX + halfW * t, centerY - halfH * (1 - t));
                    graphics.DrawLine(gridPen, centerX - halfW * t, centerY + halfH * (1 - t), centerX + halfW * (1 - t), centerY + halfH * t);
                    graphics.DrawLine(gridPen, centerX - halfW * (1 - t), centerY + halfH * t, centerX - halfW * t, centerY - halfH * (1 - t));
                    graphics.DrawLine(gridPen, centerX + halfW * t, centerY - halfH * (1 - t), centerX + halfW * (1 - t), centerY + halfH * t);
                }
            }
        }

        private void DrawIsometricLocationLabel(Graphics graphics, string location, PointF point)
        {
            using (var font = new Font("Consolas", 7.6F, FontStyle.Regular, GraphicsUnit.Point))
            using (var brush = new SolidBrush(Color.FromArgb(62, 118, 179)))
            {
                graphics.DrawString(location, font, brush, point.X - 18f, point.Y + 12f);
            }
        }

        private Rectangle DrawIsometricMapPallet(Graphics graphics, PalletRecord pallet, PointF basePoint, bool highlighted)
        {
            var dims = GetFootprintDimensionsMm(pallet);
            var width = Math.Max(28f, dims.Width * 0.032f);
            var depth = Math.Max(16f, dims.Height * 0.010f);
            var height = Math.Max(22f, Math.Min(120f, pallet.EstimatedHeightMm * 0.07f));

            var ox = basePoint.X;
            var oy = basePoint.Y;

            var top = new[]
            {
                new PointF(ox, oy - height),
                new PointF(ox + width, oy - height - depth * 0.55f),
                new PointF(ox + width + depth, oy - height),
                new PointF(ox + depth, oy - height + depth * 0.55f)
            };
            var left = new[]
            {
                new PointF(ox, oy - height),
                new PointF(ox + depth, oy - height + depth * 0.55f),
                new PointF(ox + depth, oy + depth * 0.55f),
                new PointF(ox, oy)
            };
            var right = new[]
            {
                new PointF(ox + depth, oy - height + depth * 0.55f),
                new PointF(ox + width + depth, oy - height),
                new PointF(ox + width + depth, oy),
                new PointF(ox + depth, oy + depth * 0.55f)
            };

            var topColor = GetPalletColor(pallet);
            var leftColor = ControlPaint.Dark(topColor, 0.20f);
            var rightColor = ControlPaint.Dark(topColor, 0.10f);
            var outlineColor = highlighted ? Color.FromArgb(150, 228, 255) : Color.FromArgb(42, 115, 180);

            using (var topBrush = new SolidBrush(topColor))
            using (var leftBrush = new SolidBrush(leftColor))
            using (var rightBrush = new SolidBrush(rightColor))
            using (var outlinePen = new Pen(outlineColor, highlighted ? 2f : 1.2f))
            using (var textBrush = new SolidBrush(Color.FromArgb(210, 240, 255)))
            using (var idFont = new Font("Consolas", 7.5F, FontStyle.Bold, GraphicsUnit.Point))
            using (var smallFont = new Font("Yu Gothic UI", 6.8F, FontStyle.Regular, GraphicsUnit.Point))
            {
                graphics.FillPolygon(leftBrush, left);
                graphics.FillPolygon(rightBrush, right);
                graphics.FillPolygon(topBrush, top);
                graphics.DrawPolygon(outlinePen, left);
                graphics.DrawPolygon(outlinePen, right);
                graphics.DrawPolygon(outlinePen, top);

                graphics.DrawString(pallet.PalletNumber, idFont, textBrush, ox + 4f, oy - height + 4f);
                graphics.DrawString(GetPalletFaceLabel(pallet), smallFont, textBrush, ox + 4f, oy - height + 18f);
            }

            return Rectangle.Round(new RectangleF(ox - 2f, oy - height - depth, width + depth + 6f, height + depth + 6f));
        }

        private void IsometricWarehouseBoard_MouseMove(object sender, MouseEventArgs e)
        {
            string hit = null;
            foreach (var pair in isometricPalletRects)
            {
                if (pair.Value.Contains(e.Location))
                {
                    hit = pair.Key;
                }
            }

            if (hoveredIsometricPalletNumber != hit)
            {
                hoveredIsometricPalletNumber = hit;
                var pallet = hit != null ? pallets.FirstOrDefault(item => item.PalletNumber == hit) : null;
                warehouseToolTip.SetToolTip(isometricWarehouseBoard, pallet != null ? CreatePalletTooltip(pallet) : "");
                isometricWarehouseBoard.Cursor = pallet != null ? Cursors.Hand : Cursors.Default;
                isometricWarehouseBoard.Invalidate();
            }
        }

        private void DrawGridBackground(Graphics graphics, Rectangle mapBounds)
        {
            using (var majorPen = new Pen(Color.FromArgb(20, 95, 165)))
            using (var minorPen = new Pen(Color.FromArgb(12, 58, 106)))
            using (var labelBrush = new SolidBrush(Color.FromArgb(65, 123, 184)))
            using (var labelFont = new Font("Consolas", 7.4F, FontStyle.Regular, GraphicsUnit.Point))
            {
                majorPen.DashStyle = System.Drawing.Drawing2D.DashStyle.Dash;
                minorPen.DashStyle = System.Drawing.Drawing2D.DashStyle.Dot;

                var columns = 12;
                var rows = 10;
                for (var i = 0; i <= columns; i++)
                {
                    var x = mapBounds.Left + i * mapBounds.Width / columns;
                    graphics.DrawLine(i % 2 == 0 ? majorPen : minorPen, x, mapBounds.Top, x, mapBounds.Bottom);
                    if (i < columns)
                    {
                        graphics.DrawString("X" + (i + 1).ToString("00"), labelFont, labelBrush, x + 4, mapBounds.Top - 14);
                    }
                }

                for (var i = 0; i <= rows; i++)
                {
                    var y = mapBounds.Top + i * mapBounds.Height / rows;
                    graphics.DrawLine(i % 2 == 0 ? majorPen : minorPen, mapBounds.Left, y, mapBounds.Right, y);
                    if (i < rows)
                    {
                        graphics.DrawString("Y" + (i + 1).ToString("00"), labelFont, labelBrush, mapBounds.Right + 4, y - 8);
                    }
                }
            }
        }

        private List<List<string>> GetLocationRows()
        {
            var ordered = locations.OrderBy(ParseLocationSortKey).ThenBy(item => item).ToList();
            var grouped = ordered
                .GroupBy(GetLocationPrefix)
                .OrderBy(group => group.Key)
                .Select(group => group.ToList())
                .ToList();

            if (grouped.Count == 0)
            {
                grouped.Add(new List<string> { "未設定" });
            }

            return grouped;
        }

        private Rectangle GetCellRectangle(Rectangle mapBounds, int rowIndex, int colIndex, int rowCount, int colCount)
        {
            var cellWidth = mapBounds.Width / Math.Max(1, colCount);
            var cellHeight = mapBounds.Height / Math.Max(1, rowCount);
            return new Rectangle(
                mapBounds.Left + (colIndex * cellWidth),
                mapBounds.Top + (rowIndex * cellHeight),
                cellWidth,
                cellHeight);
        }

        private void DrawLocationLabel(Graphics graphics, string location, Rectangle rect, int rowIndex, int colIndex)
        {
            using (var font = new Font("Consolas", 7.8F, FontStyle.Regular, GraphicsUnit.Point))
            using (var brush = new SolidBrush(Color.FromArgb(59, 115, 175)))
            {
                graphics.DrawString(location, font, brush, rect.Left + 6, rect.Top + 4);
            }
        }

        private Rectangle GetPalletTopRectangle(PalletRecord pallet, Rectangle cellRect)
        {
            var dims = GetFootprintDimensionsMm(pallet);
            var maxWidth = cellRect.Width - 18;
            var maxHeight = cellRect.Height - 22;
            var scale = Math.Min((float)maxWidth / dims.Width, (float)maxHeight / dims.Height);
            scale = Math.Max(0.03f, Math.Min(0.11f, scale));

            var width = Math.Max(28, (int)(dims.Width * scale));
            var height = Math.Max(22, (int)(dims.Height * scale));
            var stackedOffset = Math.Min(14, pallet.StackOrder * 4);

            var x = cellRect.Left + (cellRect.Width - width) / 2 + stackedOffset;
            var y = cellRect.Top + (cellRect.Height - height) / 2 - stackedOffset;
            return new Rectangle(x, y, width, height);
        }

        private void DrawTopPallet(Graphics graphics, PalletRecord pallet, Rectangle rect, bool highlighted)
        {
            var color = GetPalletColor(pallet);
            using (var fill = new SolidBrush(Color.FromArgb(28, color)))
            using (var border = new Pen(highlighted ? Color.FromArgb(92, 185, 255) : color, highlighted ? 2F : 1.6F))
            using (var textBrush = new SolidBrush(Color.FromArgb(198, 238, 255)))
            using (var accentBrush = new SolidBrush(color))
            using (var idFont = new Font("Consolas", 8.2F, FontStyle.Bold, GraphicsUnit.Point))
            using (var smallFont = new Font("Yu Gothic UI", 7.2F, FontStyle.Regular, GraphicsUnit.Point))
            {
                graphics.FillRectangle(fill, rect);
                graphics.DrawRectangle(border, rect);
                graphics.DrawString(pallet.PalletNumber, idFont, textBrush, rect.Left + 6, rect.Top + 4);
                graphics.DrawString(GetPalletFaceLabel(pallet), smallFont, textBrush, rect.Left + 6, rect.Top + 20);

                var stackBadgeRect = new Rectangle(rect.Right - 24, rect.Bottom - 18, 18, 12);
                graphics.FillEllipse(accentBrush, stackBadgeRect);
                graphics.DrawString((pallet.StackOrder + 1).ToString(), smallFont, Brushes.Black, stackBadgeRect.Left + 4, stackBadgeRect.Top - 1);
            }
        }

        private void WarehouseBoard_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left)
            {
                return;
            }

            var pallet = HitTestPallet(e.Location);
            if (pallet == null)
            {
                return;
            }

            draggedPalletNumber = pallet.PalletNumber;
            dragCursorPoint = e.Location;
            var rect = palletMapRects[pallet.PalletNumber];
            dragOffset = new Point(e.X - rect.Left, e.Y - rect.Top);
            SelectPalletInGrid(pallet.PalletNumber);
            warehouseBoard.Invalidate();
        }

        private void WarehouseBoard_MouseMove(object sender, MouseEventArgs e)
        {
            dragCursorPoint = e.Location;

            var pallet = HitTestPallet(e.Location);
            var palletNumber = pallet != null ? pallet.PalletNumber : null;
            if (hoveredPalletNumber != palletNumber)
            {
                hoveredPalletNumber = palletNumber;
                if (pallet != null)
                {
                    warehouseToolTip.SetToolTip(warehouseBoard, CreatePalletTooltip(pallet));
                }
                else
                {
                    warehouseToolTip.SetToolTip(warehouseBoard, "");
                }
                warehouseBoard.Invalidate();
            }

            if (draggedPalletNumber != null)
            {
                warehouseBoard.Cursor = Cursors.SizeAll;
                warehouseBoard.Invalidate();
            }
            else
            {
                warehouseBoard.Cursor = pallet != null ? Cursors.Hand : Cursors.Default;
            }
        }

        private void WarehouseBoard_MouseUp(object sender, MouseEventArgs e)
        {
            if (draggedPalletNumber == null)
            {
                return;
            }

            var pallet = pallets.FirstOrDefault(item => item.PalletNumber == draggedPalletNumber);
            var destination = GetLocationAtPoint(e.Location);

            draggedPalletNumber = null;
            warehouseBoard.Cursor = Cursors.Default;

            if (pallet != null && destination != null && !destination.Equals(pallet.LocationCode, StringComparison.OrdinalIgnoreCase))
            {
                pallet.LocationCode = destination;
                pallet.StackOrder = NextStackOrder(destination, pallet.PalletNumber);
                pallet.UpdatedAt = DateTime.Now;
                NormalizeStacks();
                SaveInventory();
                RefreshAllViews();
                SelectPalletInGrid(pallet.PalletNumber);
                return;
            }

            warehouseBoard.Invalidate();
        }

        private PalletRecord HitTestPallet(Point point)
        {
            foreach (var pallet in FilteredPallets().OrderByDescending(item => item.StackOrder))
            {
                Rectangle rect;
                if (palletMapRects.TryGetValue(pallet.PalletNumber, out rect) && rect.Contains(point))
                {
                    return pallet;
                }
            }

            return null;
        }

        private string GetLocationAtPoint(Point point)
        {
            foreach (var pair in locationMapRects)
            {
                if (pair.Value.Contains(point))
                {
                    return pair.Key;
                }
            }

            return null;
        }

        private static string GetLocationPrefix(string location)
        {
            var index = location.IndexOf('-');
            return index > 0 ? location.Substring(0, index) : location;
        }

        private static int ParseLocationSortKey(string location)
        {
            var digits = new string(location.Where(char.IsDigit).ToArray());
            int value;
            return int.TryParse(digits, out value) ? value : int.MaxValue;
        }

        private Control CreateLocationLane(string location)
        {
            var shell = new Panel
            {
                Dock = DockStyle.Fill,
                Margin = new Padding(6),
                BackColor = Color.FromArgb(247, 249, 252),
                BorderStyle = BorderStyle.FixedSingle
            };

            var title = new Label
            {
                Text = location,
                Dock = DockStyle.Top,
                Height = 34,
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Yu Gothic UI Semibold", 11F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                BackColor = Color.FromArgb(228, 236, 244)
            };

            var lane = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                AutoScroll = true,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AllowDrop = true,
                Padding = new Padding(10),
                Tag = location
            };
            lane.DragEnter += WarehouseLane_DragEnter;
            lane.DragDrop += WarehouseLane_DragDrop;

            shell.Controls.Add(lane);
            shell.Controls.Add(title);

            foreach (var pallet in FilteredPallets().Where(item => item.LocationCode == location).OrderBy(item => item.StackOrder))
            {
                lane.Controls.Add(CreatePalletCard(pallet));
            }

            return shell;
        }

        private Control CreateIsometricLane(string location)
        {
            var shell = new Panel
            {
                Dock = DockStyle.Fill,
                Margin = new Padding(6),
                BackColor = Color.FromArgb(246, 248, 251),
                BorderStyle = BorderStyle.FixedSingle
            };

            var title = new Label
            {
                Text = location,
                Dock = DockStyle.Top,
                Height = 34,
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Yu Gothic UI Semibold", 11F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                BackColor = Color.FromArgb(228, 236, 244)
            };

            var lane = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                AutoScroll = true,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                Padding = new Padding(10)
            };

            shell.Controls.Add(lane);
            shell.Controls.Add(title);

            foreach (var pallet in FilteredPallets().Where(item => item.LocationCode == location).OrderBy(item => item.StackOrder))
            {
                lane.Controls.Add(CreateIsometricPalletCard(pallet));
            }

            return shell;
        }

        private Control CreatePalletCard(PalletRecord pallet)
        {
            var card = new Panel
            {
                Width = 230,
                Height = 210,
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Margin = new Padding(0, 0, 0, 10),
                Cursor = Cursors.Hand,
                Tag = pallet.PalletNumber
            };

            var palletLabel = CreateCardLabel(pallet.PalletNumber, 30, true, Color.FromArgb(18, 102, 176));
            var metaLabel = CreateCardLabel(
                string.Format("{0} / 種類 {1} / 枚数 {2}", pallet.StackLabel, pallet.Items.Count, pallet.TotalSheets),
                24,
                false,
                Color.FromArgb(34, 47, 62));
            var topViewPanel = BuildTopViewPanel(pallet);
            var heightLabel = CreateCardLabel(
                string.Format("概算高 {0}mm", pallet.EstimatedHeightMm),
                22,
                false,
                Color.FromArgb(93, 109, 126));
            var summary = CreateCardLabel(GetPalletFaceLabel(pallet), 26, false, Color.FromArgb(93, 109, 126));
            var stackBadge = CreateStackBadge(pallet);

            card.Controls.Add(summary);
            card.Controls.Add(heightLabel);
            card.Controls.Add(topViewPanel);
            card.Controls.Add(metaLabel);
            card.Controls.Add(palletLabel);
            card.Controls.Add(stackBadge);

            var tooltipText = CreatePalletTooltip(pallet);
            ApplyTooltipRecursive(card, tooltipText);
            WireDragEvents(card);
            foreach (Control child in card.Controls)
            {
                WireDragEvents(child);
            }

            return card;
        }

        private void WireDragEvents(Control control)
        {
            control.MouseDown += PalletCard_MouseDown;
            control.DoubleClick += PalletCard_DoubleClick;
        }

        private void ApplyTooltipRecursive(Control control, string text)
        {
            warehouseToolTip.SetToolTip(control, text);
            foreach (Control child in control.Controls)
            {
                ApplyTooltipRecursive(child, text);
            }
        }

        private Control BuildTopViewPanel(PalletRecord pallet)
        {
            var shell = new Panel
            {
                Dock = DockStyle.Top,
                Height = 96,
                Padding = new Padding(8, 4, 8, 4),
                BackColor = Color.FromArgb(250, 251, 253)
            };

            var dims = GetFootprintDimensionsMm(pallet);
            var canvasWidth = 200F;
            var canvasHeight = 80F;
            var scale = Math.Min(canvasWidth / dims.Width, canvasHeight / dims.Height);
            var rectWidth = (int)Math.Max(42, dims.Width * scale);
            var rectHeight = (int)Math.Max(34, dims.Height * scale);
            var left = 8 + (int)((canvasWidth - rectWidth) / 2F);
            var top = 6 + (int)((canvasHeight - rectHeight) / 2F);

            var rectangle = new Panel
            {
                Left = left,
                Top = top,
                Width = rectWidth,
                Height = rectHeight,
                BackColor = GetPalletColor(pallet),
                BorderStyle = BorderStyle.FixedSingle,
                Tag = pallet.PalletNumber
            };

            var title = new Label
            {
                Dock = DockStyle.Top,
                Height = Math.Min(22, rectHeight / 2),
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Yu Gothic UI", 8.5F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                Text = GetFootprintLabel(pallet)
            };

            var caption = new Label
            {
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Yu Gothic UI", 7.8F, FontStyle.Regular, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                Text = GetPalletFaceLabel(pallet)
            };

            rectangle.Controls.Add(caption);
            rectangle.Controls.Add(title);
            shell.Controls.Add(rectangle);
            return shell;
        }

        private Control CreateIsometricPalletCard(PalletRecord pallet)
        {
            var dims = GetFootprintDimensionsMm(pallet);
            var scale = 0.05f;
            var width = Math.Max(70, (int)(dims.Width * scale));
            var depth = Math.Max(28, (int)(dims.Height * 0.018f));
            var height = Math.Max(20, Math.Min(78, pallet.EstimatedHeightMm / 20));

            var shell = new Panel
            {
                Width = 230,
                Height = 150,
                Margin = new Padding(0, 0, 0, 10),
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Tag = pallet.PalletNumber
            };

            var canvas = new Panel
            {
                Left = 10,
                Top = 10,
                Width = 130,
                Height = 110,
                BackColor = Color.FromArgb(248, 249, 251),
                Tag = pallet.PalletNumber
            };
            canvas.Paint += delegate(object sender, PaintEventArgs e)
            {
                DrawIsometricPallet(e.Graphics, pallet, width, depth, height);
            };

            var title = new Label
            {
                Left = 146,
                Top = 14,
                Width = 74,
                Height = 22,
                Text = pallet.PalletNumber,
                Font = new Font("Consolas", 9.5F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(18, 102, 176)
            };

            var info = new Label
            {
                Left = 146,
                Top = 40,
                Width = 74,
                Height = 72,
                Text = string.Format("{0}\n高さ {1}mm\n{2}", pallet.StackLabel, pallet.EstimatedHeightMm, GetPalletFaceLabel(pallet)),
                Font = new Font("Yu Gothic UI", 8F, FontStyle.Regular, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(60, 72, 88)
            };

            var tooltipText = CreatePalletTooltip(pallet);
            shell.Controls.Add(info);
            shell.Controls.Add(title);
            shell.Controls.Add(canvas);
            ApplyTooltipRecursive(shell, tooltipText);
            return shell;
        }

        private void DrawIsometricPallet(Graphics graphics, PalletRecord pallet, int width, int depth, int height)
        {
            graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            var originX = 18;
            var originY = 86;
            var topColor = GetPalletColor(pallet);
            var sideColor = ControlPaint.Dark(topColor, 0.12f);
            var frontColor = ControlPaint.Dark(topColor, 0.24f);

            var top = new[]
            {
                new Point(originX, originY - height),
                new Point(originX + width, originY - height),
                new Point(originX + width + depth, originY - height - depth / 2),
                new Point(originX + depth, originY - height - depth / 2)
            };

            var front = new[]
            {
                new Point(originX, originY - height),
                new Point(originX + width, originY - height),
                new Point(originX + width, originY),
                new Point(originX, originY)
            };

            var side = new[]
            {
                new Point(originX + width, originY - height),
                new Point(originX + width + depth, originY - height - depth / 2),
                new Point(originX + width + depth, originY - depth / 2),
                new Point(originX + width, originY)
            };

            using (var topBrush = new SolidBrush(topColor))
            using (var frontBrush = new SolidBrush(frontColor))
            using (var sideBrush = new SolidBrush(sideColor))
            using (var outlinePen = new Pen(Color.FromArgb(90, 102, 118)))
            {
                graphics.FillPolygon(frontBrush, front);
                graphics.FillPolygon(sideBrush, side);
                graphics.FillPolygon(topBrush, top);
                graphics.DrawPolygon(outlinePen, front);
                graphics.DrawPolygon(outlinePen, side);
                graphics.DrawPolygon(outlinePen, top);
            }

            var stackCount = pallet.StackOrder + 1;
            using (var badgeBrush = new SolidBrush(Color.FromArgb(34, 47, 62)))
            using (var textBrush = new SolidBrush(Color.White))
            using (var font = new Font("Yu Gothic UI", 8F, FontStyle.Bold, GraphicsUnit.Point))
            {
                var badge = new Rectangle(originX + width + depth - 34, originY - height - depth / 2 - 10, 28, 18);
                graphics.FillEllipse(badgeBrush, badge);
                var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
                graphics.DrawString(stackCount.ToString(), font, textBrush, badge, sf);
            }
        }

        private Control CreateStackBadge(PalletRecord pallet)
        {
            return new Label
            {
                AutoSize = false,
                Width = 44,
                Height = 22,
                Left = 176,
                Top = 6,
                TextAlign = ContentAlignment.MiddleCenter,
                BackColor = Color.FromArgb(34, 47, 62),
                ForeColor = Color.White,
                Font = new Font("Yu Gothic UI", 8.5F, FontStyle.Bold, GraphicsUnit.Point),
                Text = string.Format("{0}段", pallet.StackOrder + 1),
                Tag = pallet.PalletNumber
            };
        }

        private Size GetFootprintDimensionsMm(PalletRecord pallet)
        {
            var size = GetDominantSizeCode(pallet);
            if (size == "L")
            {
                return new Size(1200, 1300);
            }

            if (size == "OL")
            {
                return new Size(1400, 3500);
            }

            return new Size(1300, 2300);
        }

        private string GetDominantSizeCode(PalletRecord pallet)
        {
            if (pallet.Items.Count == 0)
            {
                return "LL";
            }

            return pallet.Items
                .GroupBy(item => (item.Size ?? "").Trim().ToUpperInvariant())
                .OrderByDescending(group => group.Sum(item => item.SheetCount))
                .ThenByDescending(group => GetSizeRank(group.Key))
                .Select(group => group.Key)
                .FirstOrDefault() ?? "LL";
        }

        private static int GetSizeRank(string size)
        {
            if (size == "OL") return 3;
            if (size == "LL" || size == "EL") return 2;
            if (size == "L") return 1;
            return 0;
        }

        private static Color GetPalletColor(PalletRecord pallet)
        {
            var size = pallet.Items.Select(item => (item.Size ?? "").Trim().ToUpperInvariant()).Distinct().ToList();
            if (size.Count >= 2)
            {
                return Color.FromArgb(250, 224, 170);
            }

            var dominant = size.FirstOrDefault() ?? "LL";
            if (dominant == "L") return Color.FromArgb(187, 222, 251);
            if (dominant == "OL") return Color.FromArgb(255, 205, 210);
            return Color.FromArgb(200, 230, 201);
        }

        private string GetFootprintLabel(PalletRecord pallet)
        {
            var dominant = GetDominantSizeCode(pallet);
            var dims = GetFootprintDimensionsMm(pallet);
            if (pallet.Items.Select(item => (item.Size ?? "").Trim().ToUpperInvariant()).Distinct().Count() > 1)
            {
                return string.Format("MIX / {0}x{1}", dims.Width, dims.Height);
            }

            return string.Format("{0} / {1}x{2}", dominant, dims.Width, dims.Height);
        }

        private string GetPalletFaceLabel(PalletRecord pallet)
        {
            if (pallet.Items.Count == 0)
            {
                return "空パレット";
            }

            var first = pallet.Items[0];
            if (pallet.Items.Count == 1)
            {
                return string.Format("#{0}-{1}{2}", first.PartCode, first.Size, first.ThicknessMm);
            }

            return string.Format("#{0}-{1}{2} 他{3}種", first.PartCode, first.Size, first.ThicknessMm, pallet.Items.Count - 1);
        }

        private string CreatePalletTooltip(PalletRecord pallet)
        {
            var lines = new List<string>();
            lines.Add(string.Format("パレット: {0}", pallet.PalletNumber));
            lines.Add(string.Format("位置: {0} / {1}", pallet.LocationCode, pallet.StackLabel));
            lines.Add(string.Format("概算高さ: {0}mm", pallet.EstimatedHeightMm));
            lines.Add(string.Format("内訳: 材料 {0}mm + パレット 200mm", pallet.MaterialHeightMm));
            lines.Add("明細:");

            foreach (var item in pallet.Items.Take(8))
            {
                lines.Add(string.Format(" - {0} / 高さ {1}mm", item.Identifier, item.HeightMm));
            }

            if (pallet.Items.Count > 8)
            {
                lines.Add(string.Format(" - 他 {0}件", pallet.Items.Count - 8));
            }

            return string.Join("\n", lines.ToArray());
        }

        private void PalletCard_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left)
            {
                return;
            }

            var palletNumber = FindPalletTag(sender as Control);
            if (palletNumber == null)
            {
                return;
            }

            SelectPalletInGrid(palletNumber);
            DoDragDrop(palletNumber, DragDropEffects.Move);
        }

        private void PalletCard_DoubleClick(object sender, EventArgs e)
        {
            var palletNumber = FindPalletTag(sender as Control);
            if (palletNumber != null)
            {
                SelectPalletInGrid(palletNumber);
            }
        }

        private static string FindPalletTag(Control control)
        {
            var current = control;
            while (current != null)
            {
                var tag = current.Tag as string;
                if (!string.IsNullOrEmpty(tag))
                {
                    return tag;
                }

                current = current.Parent;
            }

            return null;
        }

        private void SelectPalletInGrid(string palletNumber)
        {
            foreach (DataGridViewRow row in palletGrid.Rows)
            {
                var gridRow = row.DataBoundItem as PalletGridRow;
                if (gridRow != null && gridRow.PalletNumber == palletNumber)
                {
                    row.Selected = true;
                    palletGrid.CurrentCell = row.Cells[0];
                    break;
                }
            }
        }

        private void WarehouseLane_DragEnter(object sender, DragEventArgs e)
        {
            if (e.Data.GetDataPresent(typeof(string)))
            {
                e.Effect = DragDropEffects.Move;
            }
        }

        private void WarehouseLane_DragDrop(object sender, DragEventArgs e)
        {
            var palletNumber = e.Data.GetData(typeof(string)) as string;
            var lane = sender as FlowLayoutPanel;
            var destination = lane != null ? lane.Tag as string : null;

            if (palletNumber == null || destination == null)
            {
                return;
            }

            var pallet = pallets.FirstOrDefault(item => item.PalletNumber == palletNumber);
            if (pallet == null)
            {
                return;
            }

            pallet.LocationCode = destination;
            pallet.StackOrder = NextStackOrder(destination, pallet.PalletNumber);
            pallet.UpdatedAt = DateTime.Now;

            NormalizeStacks();
            SaveInventory();
            RefreshAllViews();
            SelectPalletInGrid(pallet.PalletNumber);
        }

        private int NextStackOrder(string location, string movingPalletNumber = null)
        {
            return pallets
                .Where(item => item.LocationCode == location && item.PalletNumber != movingPalletNumber)
                .Select(item => item.StackOrder)
                .DefaultIfEmpty(-1)
                .Max() + 1;
        }

        private void NormalizeStacks()
        {
            foreach (var location in locations)
            {
                var ordered = pallets
                    .Where(item => item.LocationCode == location)
                    .OrderBy(item => item.StackOrder)
                    .ThenBy(item => item.UpdatedAt)
                    .ToList();

                for (var i = 0; i < ordered.Count; i++)
                {
                    ordered[i].StackOrder = i;
                }
            }
        }

        private IEnumerable<PalletRecord> FilteredPallets()
        {
            var keyword = (searchTextBox != null ? searchTextBox.Text : "") ?? "";
            keyword = keyword.Trim();

            if (keyword.Length == 0)
            {
                return pallets;
            }

            return pallets.Where(pallet =>
                pallet.PalletNumber.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                || pallet.LocationCode.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                || pallet.Items.Any(item =>
                    item.Identifier.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                    || item.PartCode.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                    || item.FinishText.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0
                    || item.Grade.IndexOf(keyword, StringComparison.OrdinalIgnoreCase) >= 0));
        }

        private void RefreshPalletGrid()
        {
            palletGridBinding.DataSource = FilteredPallets()
                .OrderBy(item => item.LocationCode)
                .ThenBy(item => item.StackOrder)
                .ThenBy(item => item.PalletNumber)
                .Select(item => new PalletGridRow
                {
                    PalletNumber = item.PalletNumber,
                    LocationCode = item.LocationCode,
                    StackLabel = item.StackLabel,
                    ItemTypeCount = item.Items.Count,
                    TotalSheets = item.TotalSheets,
                    EstimatedHeightMm = item.EstimatedHeightMm,
                    SummaryText = item.SummaryText,
                    UpdatedAt = item.UpdatedAt
                })
                .ToList();
        }

        private void RefreshInventorySummaryGrid()
        {
            inventorySummaryBinding.DataSource = FilteredPallets()
                .SelectMany(
                    pallet => pallet.Items.Select(item => new { Pallet = pallet, Item = item }))
                .GroupBy(x => new
                {
                    x.Item.Identifier,
                    x.Item.PartCode,
                    x.Item.Size,
                    x.Item.ThicknessMm,
                    x.Item.FinishText,
                    x.Item.Grade
                })
                .Select(group => new InventorySummaryRow
                {
                    Identifier = group.Key.Identifier,
                    PartCode = group.Key.PartCode,
                    Size = group.Key.Size,
                    ThicknessMm = group.Key.ThicknessMm,
                    FinishText = group.Key.FinishText,
                    Grade = group.Key.Grade,
                    TotalSheets = group.Sum(x => x.Item.SheetCount),
                    TotalHeightMm = group.Sum(x => x.Item.HeightMm),
                    PalletCount = group.Select(x => x.Pallet.PalletNumber).Distinct().Count(),
                    Locations = string.Join(", ", group.Select(x => x.Pallet.LocationCode).Distinct().OrderBy(x => x).ToArray())
                })
                .OrderBy(x => x.PartCode)
                .ThenBy(x => x.Size)
                .ThenBy(x => x.ThicknessMm)
                .ToList();
        }

        private void ClearInputs()
        {
            palletNumberTextBox.Text = "";
            if (palletLocationComboBox.Items.Count > 0)
            {
                palletLocationComboBox.SelectedIndex = 0;
            }

            ClearItemInputs();
            palletGrid.ClearSelection();
            itemGrid.ClearSelection();
            selectedPalletLabel.Text = "選択中パレット: なし";
            itemGridBinding.DataSource = new List<ItemGridRow>();
            UpdateItemPreview();
            palletNumberTextBox.Focus();
        }

        private void ClearItemInputs()
        {
            partCodeTextBox.Text = "";
            sizeComboBox.Text = "LL";
            thicknessInput.Value = 10;
            finishTextBox.Text = "S/S";
            gradeComboBox.Text = "A";
            sheetCountInput.Value = 80;
            UpdateItemPreview();
        }

        private void LoadInventory()
        {
            if (!File.Exists(dataFilePath))
            {
                return;
            }

            try
            {
                using (var stream = new FileStream(dataFilePath, FileMode.Open, FileAccess.Read))
                {
                    var serializer = new DataContractJsonSerializer(typeof(InventoryStore));
                    var store = serializer.ReadObject(stream) as InventoryStore;
                    pallets.Clear();
                    locations.Clear();

                    if (store != null)
                    {
                        if (store.Pallets != null)
                        {
                            foreach (var pallet in store.Pallets)
                            {
                                pallet.Items = pallet.Items ?? new List<InventoryItemLine>();
                                pallets.Add(pallet);
                            }
                        }

                        if (store.Locations != null)
                        {
                            locations.AddRange(store.Locations);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("保存済みデータの読み込みに失敗しました。\n" + ex.Message, "読み込みエラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void SaveInventory()
        {
            var store = new InventoryStore
            {
                Pallets = pallets.OrderBy(item => item.LocationCode).ThenBy(item => item.StackOrder).ThenBy(item => item.PalletNumber).ToList(),
                Locations = locations.OrderBy(item => item).ToList()
            };

            using (var stream = new MemoryStream())
            {
                var serializer = new DataContractJsonSerializer(typeof(InventoryStore));
                serializer.WriteObject(stream, store);
                File.WriteAllText(dataFilePath, Encoding.UTF8.GetString(stream.ToArray()), Encoding.UTF8);
            }
        }

        private void ExportInventoryData()
        {
            SaveInventory();

            using (var dialog = new SaveFileDialog())
            {
                dialog.Title = "在庫データをエクスポート";
                dialog.Filter = "JSON Files (*.json)|*.json|All Files (*.*)|*.*";
                dialog.FileName = "inventory-export-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json";

                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    return;
                }

                File.Copy(dataFilePath, dialog.FileName, true);
                MessageBox.Show("エクスポートしました。\n" + dialog.FileName, "Export 完了", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }

        private void ImportInventoryData()
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Title = "在庫データをインポート";
                dialog.Filter = "JSON Files (*.json)|*.json|All Files (*.*)|*.*";

                if (dialog.ShowDialog(this) != DialogResult.OK)
                {
                    return;
                }

                try
                {
                    var imported = LoadInventoryStoreFromFile(dialog.FileName);
                    pallets.Clear();
                    locations.Clear();

                    foreach (var pallet in imported.Pallets)
                    {
                        pallet.Items = pallet.Items ?? new List<InventoryItemLine>();
                        pallets.Add(pallet);
                    }

                    locations.AddRange(imported.Locations ?? new List<string>());
                    EnsureSeedLocations();
                    RefreshLocationComboBoxes();
                    NormalizeStacks();
                    SaveInventory();
                    RefreshAllViews();
                    MessageBox.Show("インポートしました。\n" + dialog.FileName, "Import 完了", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                catch (Exception ex)
                {
                    MessageBox.Show("インポートに失敗しました。\n" + ex.Message, "Import エラー", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
        }

        private InventoryStore LoadInventoryStoreFromFile(string filePath)
        {
            using (var stream = new FileStream(filePath, FileMode.Open, FileAccess.Read))
            {
                var serializer = new DataContractJsonSerializer(typeof(InventoryStore));
                var store = serializer.ReadObject(stream) as InventoryStore;
                return store ?? new InventoryStore();
            }
        }

        private static string NormalizePalletNumber(string value)
        {
            return (value ?? "").Trim().ToUpperInvariant();
        }

        private static string NormalizePartCode(string value)
        {
            return (value ?? "").Replace("#", "").Replace("-", "").Trim().ToUpperInvariant();
        }

        private static Panel CreateCardPanel()
        {
            return new Panel
            {
                Dock = DockStyle.Fill,
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle
            };
        }

        private static Label CreateSectionTitle(string text)
        {
            return new Label
            {
                Text = text,
                Font = new Font("Yu Gothic UI Semibold", 12F, FontStyle.Bold, GraphicsUnit.Point),
                ForeColor = Color.FromArgb(34, 47, 62),
                AutoSize = true,
                Margin = new Padding(4, 4, 4, 12)
            };
        }

        private static Control CreateLabeledField(string label, Control input)
        {
            var wrapper = new Panel
            {
                Dock = DockStyle.Top,
                Height = 58,
                Margin = new Padding(4)
            };

            var title = new Label
            {
                Text = label,
                Dock = DockStyle.Top,
                Height = 18,
                ForeColor = Color.FromArgb(93, 109, 126)
            };

            input.Dock = DockStyle.Top;
            input.Height = 30;

            wrapper.Controls.Add(input);
            wrapper.Controls.Add(title);
            return wrapper;
        }

        private static Button CreatePrimaryButton(string text)
        {
            return new Button
            {
                Text = text,
                Height = 36,
                Dock = DockStyle.Top,
                BackColor = Color.FromArgb(18, 102, 176),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Margin = new Padding(4, 8, 4, 0)
            };
        }

        private static Button CreateSecondaryButton(string text)
        {
            return new Button
            {
                Text = text,
                Height = 36,
                Dock = DockStyle.Top,
                BackColor = Color.FromArgb(233, 239, 245),
                ForeColor = Color.FromArgb(34, 47, 62),
                FlatStyle = FlatStyle.Flat,
                Margin = new Padding(4, 8, 4, 0)
            };
        }

        private static Label CreateCardLabel(string text, int height, bool bold, Color color)
        {
            return new Label
            {
                Text = text,
                Dock = DockStyle.Top,
                Height = height,
                ForeColor = color,
                Font = new Font("Yu Gothic UI", bold ? 10.5F : 9F, bold ? FontStyle.Bold : FontStyle.Regular, GraphicsUnit.Point),
                Padding = new Padding(8, 4, 8, 0)
            };
        }

        private static DataGridViewTextBoxColumn CreateTextColumn(string propertyName, string title, int width)
        {
            return new DataGridViewTextBoxColumn
            {
                DataPropertyName = propertyName,
                HeaderText = title,
                Width = width,
                SortMode = DataGridViewColumnSortMode.Automatic
            };
        }
    }
}
