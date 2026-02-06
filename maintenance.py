import sqlite3
import os

# Define the columns we want to edit and how they look to the user
# Format: (Database Column Name, Display Label, Data Type)
FIELDS = [
    ('title', 'Title', str),
    ('author', 'Author', str),
    ('series_title', 'Series Title', str),
    ('series_number', 'Series Number', float),
    ('publisher', 'Publisher', str),
    ('published_year', 'Year', int),
    ('page_count', 'Page Count', int),
    ('binding', 'Binding', str),
    ('isbn', 'ISBN', str),
    ('height', 'Height (mm)', float),
    ('width', 'Width (mm)', float),
    ('weight', 'Weight (g)', float),
    ('cover_url', 'Cover URL', str),
    ('notes', 'Notes', str)
]

def get_db():
    # 1. Determine where this file (maintenance.py) is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 2. Look for the 'data' folder inside that directory
    db_path = os.path.join(base_dir, 'data', 'books.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def maintenance_mode():
    conn = get_db()
    cursor = conn.cursor()

    print("=======================================")
    print("      LIBRARY MAINTENANCE TOOL")
    print("=======================================")
    
    while True:
        print("\n---------------------------------------")
        user_input = input("Enter Book ID to edit (or 'q' to quit): ").strip()
        
        if user_input.lower() == 'q':
            print("Goodbye.")
            break

        if not user_input.isdigit():
            print("⚠️  Invalid ID. Please enter a number.")
            continue

        book_id = int(user_input)
        
        # Loop to keep editing the SAME book until user chooses to go back
        while True:
            # Re-fetch book every time to show updated values
            book = cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

            if not book:
                print(f"❌ Book ID {book_id} not found.")
                break # Break inner loop to ask for ID again

            print(f"\nEditing: {book['title']}")
            print(f"ID: {book_id}")
            print("-" * 30)

            # Display all fields with an index number
            for index, (col_name, label, _) in enumerate(FIELDS):
                # Handle None values gracefully
                current_val = book[col_name]
                if current_val is None:
                    current_val = "[Empty]"
                print(f"[{index}] {label}: {current_val}")
            
            print("-" * 30)
            choice = input("Select a field number to edit (or 'b' for back): ").strip()

            if choice.lower() == 'b':
                break # Go back to ID prompt

            if not choice.isdigit() or int(choice) >= len(FIELDS):
                print("⚠️  Invalid selection.")
                continue

            # Get the selected field info
            col_name, label, data_type = FIELDS[int(choice)]
            
            # Prompt for new value
            print(f"\nEditing '{label}' (Current: {book[col_name]})")
            new_val_str = input("Enter new value: ").strip()

            # Prepare value for database
            final_val = None
            
            if new_val_str == "":
                # If they hit enter with no text, ask if they mean NULL or keep formatting
                # For this script, empty input = DELETE data (set to NULL)
                final_val = None
            else:
                try:
                    if data_type == int:
                        final_val = int(new_val_str)
                    elif data_type == float:
                        final_val = float(new_val_str)
                    else:
                        final_val = new_val_str
                except ValueError:
                    print(f"❌ Error: Value must be a {data_type.__name__}.")
                    continue

            # Execute Update
            try:
                cursor.execute(f"UPDATE books SET {col_name} = ? WHERE id = ?", (final_val, book_id))
                conn.commit()
                print(f"✅ Updated {label}.")
            except Exception as e:
                print(f"❌ Database Error: {e}")

    conn.close()

if __name__ == '__main__':
    maintenance_mode()