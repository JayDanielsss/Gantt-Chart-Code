from gantt_utils import load_tasks, plot_gantt

def main():
    file_path   = 'Projects_sheet.numbers'  # or .xlsx
    output_path = None  # None = interactive window; 'gantt.png' = save to file

    tasks = load_tasks(file_path)
    plot_gantt(tasks, output_path)

if __name__ == "__main__":
    main()
