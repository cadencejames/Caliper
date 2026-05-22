import sqlite3
import requests # pyright: ignore[reportMissingModuleSource]
import re
import os
import csv
import io
import json
from flask import Flask, render_template, request, redirect, url_for, abort, jsonify, Response # pyright: ignore[reportMissingImports]

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

def init_db():
    conn = get_db_connection()
    try:
        conn.execute('ALTER TABLE books ADD COLUMN genre TEXT')
        conn.commit()
    except Exception:
        pass

    conn.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS book_tags (
            book_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (book_id, tag_id),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

def extract_year(date_str):
    if not date_str: return None
    match = re.search(r'\d{4}', str(date_str))
    if match: return int(match.group(0))
    return None

def clean_str(val):
    if not val: return None
    stripped = val.strip()
    return stripped if stripped else None

def normalize_genre(val):
    if not val: return None
    parts = [p.strip() for p in val.split(',') if p.strip()]
    return ', '.join(parts) if parts else None

VALID_READ_STATUSES = {'Read', 'To Read', 'DNF', 'Reference'}

def _parse_import_row(row):
    def clean_num(val, func):
        v = (val or '').strip()
        try:
            return func(v) if v else None
        except (ValueError, TypeError):
            return None

    def parse_bool(val):
        v = (val or '').strip().lower()
        return 1 if v in ('1', 'true', 'yes') else 0

    title = clean_str(row.get('title', ''))
    author = clean_str(row.get('author', ''))

    if not title or not author:
        return None, 'Missing title or author'

    read_status = clean_str(row.get('read_status', '')) or None
    if read_status and read_status not in VALID_READ_STATUSES:
        read_status = None

    return {
        'title': title,
        'author': author,
        'isbn': clean_str(row.get('isbn', '')),
        'publisher': clean_str(row.get('publisher', '')),
        'binding': clean_str(row.get('binding', '')),
        'read_status': read_status,
        'is_signed': parse_bool(row.get('is_signed', '0')),
        'page_count': clean_num(row.get('page_count', ''), int),
        'published_year': clean_num(row.get('published_year', ''), int),
        'series_title': clean_str(row.get('series_title', '')),
        'series_number': clean_num(row.get('series_number', ''), float),
        'height': clean_num(row.get('height', ''), float),
        'width': clean_num(row.get('width', ''), float),
        'weight': clean_num(row.get('weight', ''), float),
        'notes': clean_str(row.get('notes', '')),
        'cover_url': clean_str(row.get('cover_url', '')),
        'cover_filename': clean_str(row.get('cover_filename', '')),
        'genre': normalize_genre(row.get('genre', '')),
    }, None

# --- ROUTES ---

@app.route('/')
def index():
    conn = get_db_connection()
    
    # URL Parameters
    sort_param = request.args.get('sort', 'author')
    filter_param = request.args.get('filter', 'all')
    tag_param = request.args.get('tag', '')
    genre_param = request.args.get('genre', '')

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

    # 2. Build Filter Clause
    where_parts = []
    params = []

    if filter_param == 'read':
        where_parts.append("read_status = 'Read'")
    elif filter_param == 'tbr':
        where_parts.append("read_status = 'To Read'")
    elif filter_param == 'dnf':
        where_parts.append("read_status = 'DNF'")
    elif filter_param == 'reference':
        where_parts.append("read_status = 'Reference'")
    elif filter_param == 'signed':
        where_parts.append("is_signed = 1")

    if tag_param:
        where_parts.append("id IN (SELECT book_id FROM book_tags JOIN tags ON tags.id = book_tags.tag_id WHERE tags.name = ?)")
        params.append(tag_param)

    if genre_param:
        where_parts.append("(',' || REPLACE(REPLACE(genre, ' ,', ','), ', ', ',') || ',') LIKE ('%,' || ? || ',%')")
        params.append(genre_param.strip())

    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

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
    all_tags = conn.execute('SELECT name FROM tags ORDER BY name').fetchall()
    genre_rows = conn.execute('SELECT genre FROM books WHERE genre IS NOT NULL AND genre != ""').fetchall()
    conn.close()

    all_genres_set = set()
    for row in genre_rows:
        for g in row['genre'].split(','):
            g = g.strip()
            if g:
                all_genres_set.add(g)
    all_genres = sorted(all_genres_set)

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
    return render_template('index.html', books=books, current_sort=sort_param,
                           current_filter=filter_param, current_tag=tag_param,
                           current_genre=genre_param, all_tags=all_tags,
                           all_genres=all_genres, total_count=total_physical_books)

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

    book_tags = conn.execute('''
        SELECT t.id, t.name FROM tags t
        JOIN book_tags bt ON bt.tag_id = t.id
        WHERE bt.book_id = ?
        ORDER BY t.name
    ''', (book_id,)).fetchall()

    conn.close()

    book = dict(book)
    cover_filename = book.get('cover_filename')
    local_cover_path = os.path.join(app.static_folder, 'covers', cover_filename) if cover_filename else None
    if cover_filename and os.path.exists(local_cover_path):
        book['resolved_cover'] = '/static/covers/' + cover_filename
    elif book.get('cover_url'):
        book['resolved_cover'] = book['cover_url']
    else:
        book['resolved_cover'] = None

    return render_template('book_detail.html', book=book, siblings=siblings,
                           book_tags=[dict(t) for t in book_tags])

@app.route('/search')
def search_page():
    ALLOWED_FIELDS = {'height', 'width', 'weight', 'title', 'author', 'binding', 'genre'}
    ALLOWED_OPERATORS = {
        'equals', 'not_equals', 'less_than', 'greater_than', 'lte', 'gte',
        'starts_with', 'contains', 'is_null', 'is_not_null'
    }

    filter_field = request.args.get('field', '')
    filter_operator = request.args.get('operator', '')
    filter_value = request.args.get('value', '')

    where_clause = ''
    params = []

    if filter_field in ALLOWED_FIELDS and filter_operator in ALLOWED_OPERATORS:
        col = filter_field  # safe: validated against allowlist
        if filter_operator == 'equals':
            where_clause = f'WHERE {col} = ?'
            params = [filter_value]
        elif filter_operator == 'not_equals':
            where_clause = f'WHERE {col} != ?'
            params = [filter_value]
        elif filter_operator == 'less_than':
            where_clause = f'WHERE {col} < ?'
            params = [filter_value]
        elif filter_operator == 'greater_than':
            where_clause = f'WHERE {col} > ?'
            params = [filter_value]
        elif filter_operator == 'lte':
            where_clause = f'WHERE {col} <= ?'
            params = [filter_value]
        elif filter_operator == 'gte':
            where_clause = f'WHERE {col} >= ?'
            params = [filter_value]
        elif filter_operator == 'starts_with':
            where_clause = f'WHERE {col} LIKE ?'
            params = [filter_value + '%']
        elif filter_operator == 'contains':
            where_clause = f'WHERE {col} LIKE ?'
            params = ['%' + filter_value + '%']
        elif filter_operator == 'is_null':
            where_clause = f'WHERE ({col} IS NULL OR {col} = "" OR {col} = 0)'
        elif filter_operator == 'is_not_null':
            where_clause = f'WHERE {col} IS NOT NULL AND {col} != "" AND {col} != 0'

    conn = get_db_connection()
    books = conn.execute(f'''
        SELECT id, title, author, height, width, weight, binding, published_year
        FROM books
        {where_clause}
        ORDER BY author ASC, title ASC
    ''', params).fetchall()
    conn.close()

    return render_template('search.html',
        books=books,
        filter_field=filter_field,
        filter_operator=filter_operator,
        filter_value=filter_value,
        filter_active=bool(filter_field and filter_operator)
    )

if not IS_READ_ONLY:
    @app.route('/add', methods=('GET', 'POST'))
    def add_book():
        if request.method == 'POST':
            title = request.form['title'].strip()
            author = request.form['author'].strip()
            read_status = request.form.get('read_status') or None # Handle empty as None

            if not title or not author:
                return render_template('add_book.html')

            def clean_num(val, func):
                return func(val) if val else None
            raw_isbn = clean_str(request.form.get('isbn'))
            if raw_isbn and raw_isbn.lower() == 'none':
                raw_isbn = None
            book_data = {
                'title': title,
                'author': author,
                'isbn': raw_isbn,
                'publisher': clean_str(request.form.get('publisher')),
                'binding': clean_str(request.form.get('binding')),
                'read_status': read_status,
                'is_signed': 1 if request.form.get('is_signed') else 0,
                'page_count': clean_num(request.form.get('page_count'), int),
                'published_year': clean_num(request.form.get('published_year'), int),
                'series_title': clean_str(request.form.get('series_title')),
                'series_number': clean_num(request.form.get('series_number'), float),
                'height': clean_num(request.form.get('height'), float),
                'width': clean_num(request.form.get('width'), float),
                'weight': clean_num(request.form.get('weight'), float),
                'notes': clean_str(request.form.get('notes')),
                'cover_url': clean_str(request.form.get('cover_url')),
                'cover_filename': clean_str(request.form.get('cover_filename')),
                'genre': normalize_genre(request.form.get('genre')),
            }

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO books (title, author, isbn, publisher, binding, read_status, is_signed,
                                page_count, published_year, series_title, series_number,
                                height, width, weight, notes, cover_url, cover_filename, genre)
                VALUES (:title, :author, :isbn, :publisher, :binding, :read_status, :is_signed,
                        :page_count, :published_year, :series_title, :series_number,
                        :height, :width, :weight, :notes, :cover_url, :cover_filename, :genre)
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
            title = request.form['title'].strip()
            author = request.form['author'].strip()
            read_status = request.form.get('read_status') or None

            def clean_num(val, func):
                return func(val) if val else None

            raw_isbn = clean_str(request.form.get('isbn'))
            if raw_isbn and raw_isbn.lower() == 'none':
                raw_isbn = None
            book_data = {
                'title': title,
                'author': author,
                'isbn': raw_isbn,
                'publisher': clean_str(request.form.get('publisher')),
                'binding': clean_str(request.form.get('binding')),
                'read_status': read_status,
                'is_signed': 1 if request.form.get('is_signed') else 0,
                'page_count': clean_num(request.form.get('page_count'), int),
                'published_year': clean_num(request.form.get('published_year'), int),
                'series_title': clean_str(request.form.get('series_title')),
                'series_number': clean_num(request.form.get('series_number'), float),
                'height': clean_num(request.form.get('height'), float),
                'width': clean_num(request.form.get('width'), float),
                'weight': clean_num(request.form.get('weight'), float),
                'notes': clean_str(request.form.get('notes')),
                'cover_url': clean_str(request.form.get('cover_url')),
                'cover_filename': clean_str(request.form.get('cover_filename')),
                'genre': normalize_genre(request.form.get('genre')),
                'id': book_id
            }

            conn.execute('''
                UPDATE books SET title = :title, author = :author, isbn = :isbn,
                    publisher = :publisher, binding = :binding, read_status = :read_status,
                    is_signed = :is_signed, page_count = :page_count,
                    published_year = :published_year, series_title = :series_title,
                    series_number = :series_number, height = :height, width = :width,
                    weight = :weight, notes = :notes, cover_url = :cover_url,
                    cover_filename = :cover_filename, genre = :genre
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

@app.route('/api/tags')
def get_all_tags():
    conn = get_db_connection()
    tags = conn.execute('SELECT id, name FROM tags ORDER BY name').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tags])

@app.route('/tags')
def tag_management():
    if IS_READ_ONLY:
        abort(404)
    conn = get_db_connection()
    tags = conn.execute('''
        SELECT t.id, t.name, COUNT(bt.book_id) as book_count
        FROM tags t
        LEFT JOIN book_tags bt ON bt.tag_id = t.id
        GROUP BY t.id
        ORDER BY t.name
    ''').fetchall()
    conn.close()
    return render_template('tags.html', tags=[dict(t) for t in tags])

@app.route('/api/tags/<int:tag_id>/rename', methods=['POST'])
def rename_tag(tag_id):
    if IS_READ_ONLY:
        abort(404)
    name = ((request.get_json() or {}).get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    conn = get_db_connection()
    try:
        conn.execute('UPDATE tags SET name = ? WHERE id = ?', (name, tag_id))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({'error': 'A tag with that name already exists'}), 409
    conn.close()
    return jsonify({'ok': True, 'name': name})

@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    if IS_READ_ONLY:
        abort(404)
    conn = get_db_connection()
    conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/tags/merge', methods=['POST'])
def merge_tags():
    if IS_READ_ONLY:
        abort(404)
    data = request.get_json() or {}
    source_id = data.get('source_id')
    target_id = data.get('target_id')
    if not source_id or not target_id or source_id == target_id:
        return jsonify({'error': 'Invalid source or target'}), 400
    conn = get_db_connection()
    conn.execute('''
        INSERT OR IGNORE INTO book_tags (book_id, tag_id)
        SELECT book_id, ? FROM book_tags WHERE tag_id = ?
    ''', (target_id, source_id))
    conn.execute('DELETE FROM tags WHERE id = ?', (source_id,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/book/<int:book_id>/tags', methods=['POST'])
def add_book_tag(book_id):
    if IS_READ_ONLY:
        abort(404)
    name = ((request.get_json() or {}).get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Tag name required'}), 400
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (name,))
    tag = conn.execute('SELECT id FROM tags WHERE name = ?', (name,)).fetchone()
    conn.execute('INSERT OR IGNORE INTO book_tags (book_id, tag_id) VALUES (?, ?)', (book_id, tag['id']))
    conn.commit()
    conn.close()
    return jsonify({'id': tag['id'], 'name': name})

@app.route('/api/book/<int:book_id>/tags/<int:tag_id>', methods=['DELETE'])
def remove_book_tag(book_id, tag_id):
    if IS_READ_ONLY:
        abort(404)
    conn = get_db_connection()
    conn.execute('DELETE FROM book_tags WHERE book_id = ? AND tag_id = ?', (book_id, tag_id))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

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

        ALLOWED_FIELDS = {'height', 'width', 'weight', 'title', 'author', 'binding', 'genre'}
        ALLOWED_OPERATORS = {
            'equals', 'not_equals', 'less_than', 'greater_than', 'lte', 'gte',
            'starts_with', 'contains', 'is_null', 'is_not_null'
        }

        filter_field = request.args.get('field', '')
        filter_operator = request.args.get('operator', '')
        filter_value = request.args.get('value', '')

        extra_clause = ''
        extra_params = []

        if filter_field in ALLOWED_FIELDS and filter_operator in ALLOWED_OPERATORS:
            col = filter_field  # safe: validated against allowlist
            if filter_operator == 'equals':
                extra_clause = f' AND {col} = ?'
                extra_params = [filter_value]
            elif filter_operator == 'not_equals':
                extra_clause = f' AND {col} != ?'
                extra_params = [filter_value]
            elif filter_operator == 'less_than':
                extra_clause = f' AND {col} < ?'
                extra_params = [filter_value]
            elif filter_operator == 'greater_than':
                extra_clause = f' AND {col} > ?'
                extra_params = [filter_value]
            elif filter_operator == 'lte':
                extra_clause = f' AND {col} <= ?'
                extra_params = [filter_value]
            elif filter_operator == 'gte':
                extra_clause = f' AND {col} >= ?'
                extra_params = [filter_value]
            elif filter_operator == 'starts_with':
                extra_clause = f' AND {col} LIKE ?'
                extra_params = [filter_value + '%']
            elif filter_operator == 'contains':
                extra_clause = f' AND {col} LIKE ?'
                extra_params = ['%' + filter_value + '%']
            elif filter_operator == 'is_null':
                extra_clause = f' AND ({col} IS NULL OR {col} = "" OR {col} = 0)'
            elif filter_operator == 'is_not_null':
                extra_clause = f' AND {col} IS NOT NULL AND {col} != "" AND {col} != 0'

        missing_dims = conn.execute(f'''
            SELECT * FROM books
            WHERE ((height IS NULL OR height = 0)
            OR (width IS NULL OR width = 0)
            OR (weight IS NULL OR weight = 0))
            {extra_clause}
            ORDER BY author ASC, series_title ASC, series_number ASC, title ASC
        ''', extra_params).fetchall()

        conn.close()
        return render_template('audit.html',
            missing_isbn=missing_isbn,
            missing_dims=missing_dims,
            filter_field=filter_field,
            filter_operator=filter_operator,
            filter_value=filter_value
        )

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

@app.route('/stats')
def stats_page():
    conn = get_db_connection()

    total_books = conn.execute('SELECT COUNT(*) FROM books').fetchone()[0]
    signed_count = conn.execute('SELECT COUNT(*) FROM books WHERE is_signed = 1').fetchone()[0]

    tbr_pages = conn.execute(
        "SELECT COALESCE(SUM(page_count), 0) FROM books WHERE read_status = 'To Read' AND page_count IS NOT NULL"
    ).fetchone()[0]

    total_weight_g = conn.execute(
        'SELECT COALESCE(SUM(weight), 0) FROM books WHERE weight IS NOT NULL'
    ).fetchone()[0]

    total_height_mm = conn.execute(
        'SELECT COALESCE(SUM(height), 0) FROM books WHERE height IS NOT NULL'
    ).fetchone()[0]

    oldest_book = conn.execute(
        'SELECT title, author, published_year FROM books WHERE published_year IS NOT NULL ORDER BY published_year ASC LIMIT 1'
    ).fetchone()

    longest_book = conn.execute(
        'SELECT title, author, page_count FROM books WHERE page_count IS NOT NULL ORDER BY page_count DESC LIMIT 1'
    ).fetchone()

    dnf_count = conn.execute(
        "SELECT COUNT(*) FROM books WHERE read_status = 'DNF'"
    ).fetchone()[0]

    status_rows = conn.execute(
        "SELECT COALESCE(read_status, 'No Status') as status, COUNT(*) as count FROM books GROUP BY status"
    ).fetchall()
    status_counts = {row['status']: row['count'] for row in status_rows}

    format_rows = conn.execute(
        "SELECT COALESCE(NULLIF(TRIM(binding), ''), 'Unknown') as binding, COUNT(*) as count FROM books GROUP BY TRIM(binding) ORDER BY count DESC"
    ).fetchall()
    format_counts = [{'binding': row['binding'], 'count': row['count']} for row in format_rows]

    unfinished_series = conn.execute('''
        SELECT
            series_title,
            COUNT(*) as total_owned,
            SUM(is_read) as read_count
        FROM (
            SELECT
                series_title,
                title,
                MAX(CASE WHEN read_status = 'Read' THEN 1 ELSE 0 END) as is_read
            FROM books
            WHERE series_title IS NOT NULL AND series_title != ''
            GROUP BY series_title, title
        ) deduped
        GROUP BY series_title
        HAVING read_count > 0 AND read_count < total_owned
        ORDER BY series_title ASC
    ''').fetchall()

    conn.close()

    dnf_rate = round(dnf_count / total_books * 100, 1) if total_books > 0 else 0

    return render_template('stats.html',
        total_books=total_books,
        signed_count=signed_count,
        tbr_pages=tbr_pages,
        total_weight_kg=round(total_weight_g / 1000, 1),
        total_height_m=round(total_height_mm / 1000, 1),
        oldest_book=dict(oldest_book) if oldest_book else None,
        longest_book=dict(longest_book) if longest_book else None,
        dnf_count=dnf_count,
        dnf_rate=dnf_rate,
        status_counts=status_counts,
        format_counts=format_counts,
        unfinished_series=[dict(s) for s in unfinished_series]
    )

@app.route('/random')
def random_book():
    conn = get_db_connection()
    book = conn.execute(
        "SELECT * FROM books WHERE read_status = 'To Read' ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()

    if book:
        book = dict(book)
        cover_filename = book.get('cover_filename')
        local_cover_path = os.path.join(app.static_folder, 'covers', cover_filename) if cover_filename else None
        if cover_filename and local_cover_path and os.path.exists(local_cover_path):
            book['resolved_cover'] = '/static/covers/' + cover_filename
        elif book.get('cover_url'):
            book['resolved_cover'] = book['cover_url']
        else:
            book['resolved_cover'] = None

    return render_template('random.html', book=book)

if not IS_READ_ONLY:
    @app.route('/export')
    def export_books():
        conn = get_db_connection()
        books = conn.execute('''
            SELECT title, author, isbn, publisher, binding, read_status, is_signed,
                   page_count, published_year, series_title, series_number,
                   height, width, weight, notes, cover_url, cover_filename
            FROM books ORDER BY author ASC, title ASC
        ''').fetchall()
        conn.close()

        fieldnames = ['title', 'author', 'isbn', 'publisher', 'binding', 'read_status',
                      'is_signed', 'page_count', 'published_year', 'series_title',
                      'series_number', 'height', 'width', 'weight', 'notes',
                      'cover_url', 'cover_filename', 'genre']
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for book in books:
            writer.writerow(dict(book))

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=caliper_library.csv'}
        )

if not IS_READ_ONLY:
    @app.route('/import', methods=('GET', 'POST'))
    def import_books():
        if request.method == 'POST':
            file = request.files.get('csv_file')

            if not file or not file.filename:
                return render_template('import.html', mode='upload', error='No file selected.')

            if not file.filename.lower().endswith('.csv'):
                return render_template('import.html', mode='upload',
                                       error=f'"{file.filename}" is not a CSV file. Only .csv files are supported.')

            try:
                stream = io.StringIO(file.stream.read().decode('utf-8-sig'))
                reader = csv.DictReader(stream)

                ready = []
                skipped = []

                for i, row in enumerate(reader, start=2):
                    book, reason = _parse_import_row(row)
                    if book:
                        ready.append(book)
                    else:
                        skipped.append({
                            'row': i,
                            'title': (row.get('title') or '').strip() or '—',
                            'author': (row.get('author') or '').strip() or '—',
                            'reason': reason
                        })

            except Exception:
                return render_template('import.html', mode='upload',
                                       error='Could not parse the file. Make sure it is a valid CSV.')

            if not ready and not skipped:
                return render_template('import.html', mode='upload', error='The file appears to be empty.')

            confirmed_data = json.dumps(ready)
            return render_template('import.html', mode='preview',
                                   ready=ready, skipped=skipped,
                                   confirmed_data=confirmed_data)

        imported = request.args.get('imported')
        error = request.args.get('error')
        return render_template('import.html', mode='upload', imported=imported, error=error)

if not IS_READ_ONLY:
    @app.route('/import/confirm', methods=('POST',))
    def import_confirm():
        try:
            rows = json.loads(request.form.get('confirmed_data', '[]'))
        except Exception:
            return redirect(url_for('import_books', error='Invalid import data.'))

        conn = get_db_connection()
        try:
            for book in rows:
                conn.execute('''
                    INSERT INTO books (title, author, isbn, publisher, binding, read_status,
                        is_signed, page_count, published_year, series_title, series_number,
                        height, width, weight, notes, cover_url, cover_filename, genre)
                    VALUES (:title, :author, :isbn, :publisher, :binding, :read_status,
                            :is_signed, :page_count, :published_year, :series_title, :series_number,
                            :height, :width, :weight, :notes, :cover_url, :cover_filename, :genre)
                ''', book)
            conn.commit()
        except Exception:
            conn.rollback()
            conn.close()
            return redirect(url_for('import_books', error='Database error during import. No books were added.'))

        conn.close()
        return redirect(url_for('import_books', imported=len(rows)))

init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)