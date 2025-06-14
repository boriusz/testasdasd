from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import time
import psycopg2

# Inicjalizacja aplikacji Flask
app = Flask(__name__)
app.secret_key = 'tajny-klucz-sesji-2024'

# Konfiguracja bazy danych
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL',
                                                       'postgresql://admin:haslo123@db:5432/wydarzenia_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicjalizacja SQLAlchemy
db = SQLAlchemy(app)

# Hasła dostępu (nieszyfrowane jak w wymaganiach)
HASLA_DOSTEPU = {
    'admin': 'admin123',
    'event1': 'haslo1',
    'event2': 'haslo2'
}


# Model danych - tabela wpisów
class Wpis(db.Model):
    __tablename__ = 'wpisy'

    id = db.Column(db.Integer, primary_key=True)
    imie = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    telefon = db.Column(db.String(20), nullable=True)
    wiadomosc = db.Column(db.Text, nullable=True)
    data_wpisu = db.Column(db.DateTime, default=datetime.utcnow)
    kategoria = db.Column(db.String(50), default='ogolne')

    def __repr__(self):
        return f'<Wpis {self.id}: {self.imie}>'

    def to_dict(self):
        """Konwersja obiektu do słownika"""
        return {
            'id': self.id,
            'imie': self.imie,
            'email': self.email,
            'telefon': self.telefon,
            'wiadomosc': self.wiadomosc,
            'data_wpisu': self.data_wpisu,
            'kategoria': self.kategoria
        }


def wait_for_database(max_retries=30, delay=2):
    """Oczekiwanie na dostępność bazy danych"""
    database_url = os.environ.get('DATABASE_URL', 'postgresql://admin:haslo123@db:5432/wydarzenia_db')

    for attempt in range(max_retries):
        try:
            # Próba połączenia z bazą danych
            conn = psycopg2.connect(database_url)
            conn.close()
            print(f"Połączenie z bazą danych udane po {attempt + 1} próbach")
            return True
        except psycopg2.OperationalError as e:
            print(f"Próba {attempt + 1}/{max_retries}: Oczekiwanie na bazę danych... ({e})")
            time.sleep(delay)

    print("BŁĄD: Nie udało się połączyć z bazą danych po wszystkich próbach!")
    return False


def init_database():
    """Inicjalizacja bazy danych"""
    try:
        # Najpierw poczekaj na bazę danych
        if not wait_for_database():
            return False

        with app.app_context():
            db.create_all()
            print("Baza danych zainicjalizowana pomyślnie")
            return True
    except Exception as e:
        print(f"Błąd inicjalizacji bazy danych: {e}")
        return False


@app.route('/')
def index():
    """Strona główna z logowaniem"""
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    """Logowanie użytkownika"""
    haslo = request.form.get('haslo')

    # Sprawdzenie hasła
    kategoria_znaleziona = None
    for kategoria, poprawne_haslo in HASLA_DOSTEPU.items():
        if haslo == poprawne_haslo:
            kategoria_znaleziona = kategoria
            break

    if kategoria_znaleziona:
        session['zalogowany'] = True
        session['kategoria'] = kategoria_znaleziona
        return redirect(url_for('formularz'))
    else:
        flash('Nieprawidłowe hasło!')
        return redirect(url_for('index'))


@app.route('/formularz')
def formularz():
    """Formularz do wypełnienia (tylko dla zalogowanych)"""
    if not session.get('zalogowany'):
        flash('Musisz się zalogować!')
        return redirect(url_for('index'))

    return render_template('formularz.html', kategoria=session.get('kategoria'))


@app.route('/zapisz', methods=['POST'])
def zapisz():
    """Zapisanie danych z formularza"""
    if not session.get('zalogowany'):
        flash('Musisz się zalogować!')
        return redirect(url_for('index'))

    try:
        # Pobranie danych z formularza
        imie = request.form.get('imie', '').strip()
        email = request.form.get('email', '').strip()
        telefon = request.form.get('telefon', '').strip()
        wiadomosc = request.form.get('wiadomosc', '').strip()
        kategoria = session.get('kategoria', 'ogolne')

        # Walidacja podstawowych danych
        if not imie or not email:
            flash('Imię i email są wymagane!')
            return redirect(url_for('formularz'))

        # Utworzenie nowego wpisu
        nowy_wpis = Wpis(
            imie=imie,
            email=email,
            telefon=telefon if telefon else None,
            wiadomosc=wiadomosc if wiadomosc else None,
            kategoria=kategoria
        )

        # Zapisanie do bazy danych
        db.session.add(nowy_wpis)
        db.session.commit()

        flash(f'Dane zostały zapisane pomyślnie! ID wpisu: {nowy_wpis.id}')

    except Exception as e:
        db.session.rollback()
        flash(f'Błąd zapisu: {str(e)}')
        print(f"Błąd zapisu do bazy: {e}")

    return redirect(url_for('formularz'))


@app.route('/lista')
def lista():
    """Lista wszystkich wpisów (tylko dla admina)"""
    if not session.get('zalogowany') or session.get('kategoria') != 'admin':
        flash('Brak uprawnień!')
        return redirect(url_for('index'))

    print("hello")
    try:
        # Pobranie wszystkich wpisów, sortowanie od najnowszych
        wpisy = Wpis.query.order_by(Wpis.data_wpisu.desc()).all()
        print(wpisy)
        return render_template('lista.html', wpisy=wpisy)

    except Exception as e:
        flash(f'Błąd odczytu danych: {str(e)}')
        return render_template('lista.html', wpisy=[])


@app.route('/lista/<kategoria>')
def lista_kategoria(kategoria):
    """Lista wpisów z określonej kategorii"""
    if not session.get('zalogowany'):
        flash('Musisz się zalogować!')
        return redirect(url_for('index'))

    # Admin może przeglądać wszystkie kategorie
    if session.get('kategoria') != 'admin' and session.get('kategoria') != kategoria:
        flash('Możesz przeglądać tylko swoje wpisy!')
        return redirect(url_for('formularz'))

    try:
        wpisy = Wpis.query.filter_by(kategoria=kategoria).order_by(Wpis.data_wpisu.desc()).all()
        return render_template('lista.html', wpisy=wpisy, kategoria_filter=kategoria)

    except Exception as e:
        flash(f'Błąd odczytu danych: {str(e)}')
        return render_template('lista.html', wpisy=[], kategoria_filter=kategoria)


@app.route('/stats')
def stats():
    """Statystyki wpisów (tylko dla admina)"""
    if not session.get('zalogowany') or session.get('kategoria') != 'admin':
        flash('Brak uprawnień!')
        return redirect(url_for('index'))

    try:
        # Statystyki podstawowe
        total_wpisy = Wpis.query.count()
        wpisy_dzis = Wpis.query.filter(
            db.func.date(Wpis.data_wpisu) == datetime.utcnow().date()
        ).count()

        # Statystyki per kategoria
        stats_kategorie = db.session.query(
            Wpis.kategoria,
            db.func.count(Wpis.id).label('liczba')
        ).group_by(Wpis.kategoria).all()

        return render_template('stats.html',
                               total_wpisy=total_wpisy,
                               wpisy_dzis=wpisy_dzis,
                               stats_kategorie=stats_kategorie)

    except Exception as e:
        flash(f'Błąd pobierania statystyk: {str(e)}')
        return redirect(url_for('lista'))


@app.route('/wyloguj')
def wyloguj():
    """Wylogowanie użytkownika"""
    session.clear()
    flash('Zostałeś wylogowany')
    return redirect(url_for('index'))


# Obsługa błędów
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback()
    return render_template('500.html'), 500


if __name__ == '__main__':
    print("Startowanie aplikacji... 123")
    if init_database():
        print("Aplikacja gotowa do działania!")
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        print("BŁĄD: Nie udało się zainicjalizować bazy danych. Aplikacja nie zostanie uruchomiona.")
        exit(1)