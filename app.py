import sqlite3
import requests # pyright: ignore[reportMissingModuleSource]
import re
import os
from flask import Flask, render_template, request, redirect, url_for, abort, jsonify # pyright: ignore[reportMissingImports]

app = Flask(__name__)

# Determine if we are in Admin Mode or Public Read-Only Mode
# Default to 'ADMIN' if not specified (for local dev safety)
APP_MODE = os.environ.get('APP_MODE', 'ADMIN').upper()
IS_READ_ONLY = (APP_MODE == 'PUBLIC')

# This 'context processor' makes the 'is_read_only' variable 
# available to EVERY HTML template automatically.
@app.context_processor
def inject_mode():
    return dict(is_read_only=IS_READ_ONLY)

def get_db_connection():
    # 1. Determine where this file (app.py) is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # 2. Look for the 'data' folder inside that directory
    db_path = os.path.join(base_dir, 'data', 'books.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def extract_year(date_str):
    if not date_str: return None
    match = re.search(r'\d{4}', str(date_str))
    if match: return int(match.group(0))
    return None

# --- ROUTES ---

@app.route('/')
def index():
    conn = get_db_connection()
    
    # URL Parameters
    sort_param = request.args.get('sort', 'author')
    filter_param = request.args.get('filter', 'all')

    # 1. Base Query
    base_query = """
        SELECT 
            MIN(id) as id,
            title, 
            author, 
            series_title, 
            series_number, 
            MIN(published_year) as published_year,
            COUNT(*) as copy_count,
            GROUP_CONCAT(binding, ',') as all_bindings,
            read_status -- We need this for filtering logic
        FROM books 
    """

    # 2. Add Filter Clause
    where_clause = ""
    params = []
    
    if filter_param == 'read':
        where_clause = "WHERE read_status = 'Read'"
    elif filter_param == 'tbr':
        where_clause = "WHERE read_status = 'To Read'"
    elif filter_param == 'dnf':
        where_clause = "WHERE read_status = 'DNF'"
    elif filter_param == 'signed':
        where_clause = "WHERE is_signed = 1"

    # 3. Add Sort Clause
    if sort_param == 'newest':
        order_clause = 'ORDER BY MAX(id) DESC'
    elif sort_param == 'oldest':
        order_clause = 'ORDER BY MIN(id) ASC'
    elif sort_param == 'title':
        order_clause = 'ORDER BY title ASC'
    elif sort_param == 'year_asc':
        order_clause = 'ORDER BY MIN(published_year) ASC'
    elif sort_param == 'year_desc':
        order_clause = 'ORDER BY MAX(published_year) DESC'
    else:
        # DEFAULT: The "Canonical Library Sort"
        # 1. Author
        # 2. Series Title (group series together)
        # 3. Series Number (order within series)
        # 4. Title (fallback for standalones or ties)
        order_clause = '''
            ORDER BY 
            author ASC, 
            series_title ASC, 
            series_number ASC, 
            title ASC
        '''

    # Combine Query
    final_query = f"{base_query} {where_clause} GROUP BY title, author {order_clause}"
    
    books_raw = conn.execute(final_query, params).fetchall()
    conn.close()

    # Process Bindings
    books = []
    for b in books_raw:
        book = dict(b)
        if book['all_bindings']:
            formats = [f.strip() for f in book['all_bindings'].split(',') if f.strip()]
            unique_formats = sorted(list(set(formats)))
            book['display_formats'] = ", ".join(unique_formats)
        else:
            book['display_formats'] = "Unknown"
        books.append(book)

    total_physical_books = sum(book['copy_count'] for book in books)
    # Pass both sort and filter params back to template
    return render_template('index.html', books=books, current_sort=sort_param, current_filter=filter_param, total_count=total_physical_books)

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    
    if book is None:
        conn.close()
        abort(404)
        
    siblings = conn.execute('''
        SELECT id, binding, published_year, notes 
        FROM books 
        WHERE title = ? AND author = ? AND id != ?
        ORDER BY id ASC
    ''', (book['title'], book['author'], book_id)).fetchall()

    conn.close()
    return render_template('book_detail.html', book=book, siblings=siblings)

if not IS_READ_ONLY:
    @app.route('/add', methods=('GET', 'POST'))
    def add_book():
        if request.method == 'POST':
            title = request.form['title']
            author = request.form['author']
            read_status = request.form.get('read_status') or None # Handle empty as None
            
            if not title or not author:
                return render_template('add_book.html')

            def clean_num(val, func):
                return func(val) if val else None
            raw_isbn = request.form.get('isbn')
            if raw_isbn and raw_isbn.strip().lower() == 'none':
                raw_isbn = None
            elif raw_isbn and raw_isbn.strip() == '':
                raw_isbn = None
            book_data = {
                'title': title,
                'author': author,
                'isbn': raw_isbn,
                'publisher': request.form.get('publisher'),
                'binding': request.form.get('binding'),
                'read_status': read_status,
                'is_signed': 1 if request.form.get('is_signed') else 0,
                'page_count': clean_num(request.form.get('page_count'), int),
                'published_year': clean_num(request.form.get('published_year'), int),
                'series_title': request.form.get('series_title') or None,
                'series_number': clean_num(request.form.get('series_number'), float),
                'height': clean_num(request.form.get('height'), float),
                'width': clean_num(request.form.get('width'), float),
                'weight': clean_num(request.form.get('weight'), float),
                'notes': request.form.get('notes'),
                'cover_url': request.form.get('cover_url')
            }

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO books (title, author, isbn, publisher, binding, read_status, is_signed,
                                page_count, published_year, series_title, series_number, 
                                height, width, weight, notes, cover_url)
                VALUES (:title, :author, :isbn, :publisher, :binding, :read_status, :is_signed,
                        :page_count, :published_year, :series_title, :series_number, 
                        :height, :width, :weight, :notes, :cover_url)
            ''', book_data)
            new_id = cur.lastrowid

            # --- NEW: SYNC LOGIC ---
            # If checkbox is checked, apply read_status to all OTHER copies
            if request.form.get('sync_status'):
                cur.execute('''
                    UPDATE books 
                    SET read_status = ? 
                    WHERE title = ? AND author = ? AND id != ?
                ''', (read_status, title, author, new_id))
            # -----------------------

            conn.commit()
            conn.close()

            return redirect(url_for('book_detail', book_id=new_id))

        return render_template('add_book.html')

if not IS_READ_ONLY:
    @app.route('/book/<int:book_id>/edit', methods=('GET', 'POST'))
    def edit_book(book_id):
        conn = get_db_connection()
        book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()

        if book is None:
            conn.close()
            abort(404)

        if request.method == 'POST':
            title = request.form['title']
            author = request.form['author']
            read_status = request.form.get('read_status') or None

            def clean_num(val, func):
                return func(val) if val else None

            series_title = request.form.get('series_title')
            if not series_title or series_title.strip() == "":
                series_title = None
            raw_isbn = request.form.get('isbn')
            if raw_isbn and raw_isbn.strip().lower() == 'none':
                raw_isbn = None
            elif raw_isbn and raw_isbn.strip() == '':
                raw_isbn = None
            book_data = {
                'title': title,
                'author': author,
                'isbn': raw_isbn,
                'publisher': request.form.get('publisher'),
                'binding': request.form.get('binding'),
                'read_status': read_status,
                'is_signed': 1 if request.form.get('is_signed') else 0,
                'page_count': clean_num(request.form.get('page_count'), int),
                'published_year': clean_num(request.form.get('published_year'), int),
                'series_title': series_title,
                'series_number': clean_num(request.form.get('series_number'), float),
                'height': clean_num(request.form.get('height'), float),
                'width': clean_num(request.form.get('width'), float),
                'weight': clean_num(request.form.get('weight'), float),
                'notes': request.form.get('notes'),
                'cover_url': request.form.get('cover_url'),
                'id': book_id
            }

            conn.execute('''
                UPDATE books SET title = :title, author = :author, isbn = :isbn,
                    publisher = :publisher, binding = :binding, read_status = :read_status,
                    is_signed = :is_signed, page_count = :page_count,
                    published_year = :published_year, series_title = :series_title,
                    series_number = :series_number, height = :height, width = :width,
                    weight = :weight, notes = :notes, cover_url = :cover_url
                WHERE id = :id
            ''', book_data)

            if request.form.get('sync_status'):
                conn.execute('''
                    UPDATE books 
                    SET read_status = ? 
                    WHERE title = ? AND author = ? AND id != ?
                ''', (read_status, title, author, book_id))

            conn.commit()
            conn.close()
            if request.args.get('origin') == 'audit':
                return redirect(url_for('audit_page'))
                
            return redirect(url_for('book_detail', book_id=book_id))

        conn.close()
        return render_template('add_book.html', book=book)

if not IS_READ_ONLY:
    @app.route('/book/<int:book_id>/delete', methods=('POST',))
    def delete_book(book_id):
        conn = get_db_connection()
        conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))

@app.route('/api/lookup', methods=['POST'])
def lookup_isbn():
    data = request.get_json()
    isbn = data.get('isbn')
    clean_isbn = ''.join(filter(str.isdigit, isbn))

    if not clean_isbn:
        return jsonify({'found': False})

    try:
        # 1. Open Library Fetch
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json"
        response = requests.get(url)
        if response.status_code == 200:
            json_data = response.json()
            key = f"ISBN:{clean_isbn}"
            if key in json_data:
                book = json_data[key]
                
                # Format Author
                authors_str = "Unknown"
                if 'authors' in book:
                    raw_names = [a['name'] for a in book['authors']]
                    formatted_names = []
                    for name in raw_names:
                        parts = name.strip().split(' ')
                        if len(parts) > 1:
                            last = parts[-1]
                            first = " ".join(parts[:-1])
                            formatted_names.append(f"{last}, {first}")
                        else:
                            formatted_names.append(name)
                    authors_str = " & ".join(formatted_names)
                
                # Cover
                cover = ""
                if 'cover' in book:
                    cover = book['cover'].get('large', book['cover'].get('medium', ''))

                # --- NEW: CHECK LOCAL DB FOR READ STATUS ---
                conn = get_db_connection()
                # Check if we have ANY copy of this book (same title/author) that is not NULL
                existing = conn.execute('''
                    SELECT read_status FROM books 
                    WHERE title = ? AND author = ? AND read_status IS NOT NULL 
                    LIMIT 1
                ''', (book.get('title', ''), authors_str)).fetchone()
                conn.close()

                suggested_status = ""
                if existing:
                    suggested_status = existing['read_status']
                # -------------------------------------------

                return jsonify({
                    'found': True,
                    'title': book.get('title', ''),
                    'author': authors_str,
                    'published_year': extract_year(book.get('publish_date')),
                    'page_count': book.get('number_of_pages'),
                    'publisher': book.get('publishers', [{'name': ''}])[0].get('name'),
                    'cover_url': cover,
                    'suggested_status': suggested_status # Sending this back to frontend
                })
    except:
        pass
    
    return jsonify({'found': False})

if not IS_READ_ONLY:
    @app.route('/audit')
    def audit_page():
        conn = get_db_connection()
        
        # MODIFIED QUERY: Exclude books where no_isbn = 1
        missing_isbn = conn.execute('''
            SELECT * FROM books 
            WHERE (isbn IS NULL OR isbn = '') 
            AND (no_isbn IS NULL OR no_isbn = 0) 
            ORDER BY author ASC, title ASC
        ''').fetchall()
        
        missing_dims = conn.execute('''
            SELECT * FROM books 
            WHERE (height IS NULL OR height = 0) 
            OR (width IS NULL OR width = 0) 
            ORDER BY author ASC, series_title ASC, series_number ASC, title ASC
        ''').fetchall()
        
        conn.close()
        return render_template('audit.html', missing_isbn=missing_isbn, missing_dims=missing_dims)

if not IS_READ_ONLY:
    @app.route('/api/mark_no_isbn', methods=['POST'])
    def mark_no_isbn():
        data = request.get_json()
        book_id = data.get('id')
        
        if book_id:
            conn = get_db_connection()
            conn.execute('UPDATE books SET no_isbn = 1 WHERE id = ?', (book_id,))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        return jsonify({'success': False}), 400

if not IS_READ_ONLY:
    @app.route('/api/quick_update', methods=['POST'])
    def quick_update():
        """API for the Inline Edit tool (Physical Audit)"""
        data = request.get_json()
        book_id = data.get('id')
        
        # Helper to clean numbers
        def clean(val):
            return float(val) if val and val != "" else None

        if book_id:
            conn = get_db_connection()
            conn.execute('''
                UPDATE books 
                SET height = ?, width = ?, weight = ? 
                WHERE id = ?
            ''', (clean(data.get('height')), clean(data.get('width')), clean(data.get('weight')), book_id))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        return jsonify({'success': False}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)