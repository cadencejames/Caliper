import sqlite3
import os

def create_example_database():
    # 1. Ensure the 'data' directory exists
    if not os.path.exists('data'):
        os.makedirs('data')
        print("📁 Created 'data' directory.")

    db_path = os.path.join('data', 'example_books.db')

    # 2. Connect (this creates the file)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 3. Drop table if exists (Clean Slate)
    cursor.execute('DROP TABLE IF EXISTS books')

    # 4. Create the Table with the exact schema we built
    cursor.execute('''
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT,
            publisher TEXT,
            binding TEXT,
            page_count INTEGER,
            published_year INTEGER,
            series_title TEXT,
            series_number REAL,
            height REAL,
            width REAL,
            weight REAL,
            notes TEXT,
            cover_url TEXT,
            read_status TEXT DEFAULT NULL,
            is_signed INTEGER DEFAULT 0,
            no_isbn INTEGER DEFAULT 0
        )
    ''')
    print("✅ Created 'books' table structure.")

    # 5. Insert Sample Data
    # We add a few books to demonstrate Series, Grouping, and Badges
    sample_books = [
        (
            "Dune", "Herbert, Frank", "9780441172719", "Ace", "Paperback", 
            896, 1965, "Dune", 1.0, 
            105.0, 170.0, 300.0, "The classic sci-fi novel.", 
            "https://covers.openlibrary.org/b/id/9253497-L.jpg", "Read", 0, 0
        ),
        (
            "Dune Messiah", "Herbert, Frank", "9780441172696", "Ace", "Mass Market Paperback", 
            350, 1969, "Dune", 2.0, 
            105.0, 170.0, 200.0, None, 
            "https://covers.openlibrary.org/b/id/9255050-L.jpg", "To Read", 0, 0
        ),
        (
            "The Hobbit", "Tolkien, J.R.R.", "9780547928227", "Houghton Mifflin", "Hardcover", 
            300, 1937, "The Lord of the Rings", 0.0, 
            140.0, 210.0, 500.0, "Special Collector's Edition", 
            "https://covers.openlibrary.org/b/id/8406786-L.jpg", "Read", 1, 0
        ),
        (
            "Unknown Old Book", "Anonymous", None, "Old Press", "Hardcover", 
            120, 1890, None, None, 
            120.0, 180.0, 300.0, "Found in attic. No ISBN.", 
            None, None, 0, 1  # no_isbn = 1
        )
    ]

    cursor.executemany('''
        INSERT INTO books (
            title, author, isbn, publisher, binding, 
            page_count, published_year, series_title, series_number, 
            height, width, weight, notes, 
            cover_url, read_status, is_signed, no_isbn
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', sample_books)

    conn.commit()
    conn.close()
    print(f"✅ Inserted {len(sample_books)} sample books.")
    print(f"🎉 Database ready at: {db_path}")

if __name__ == '__main__':
    create_example_database()