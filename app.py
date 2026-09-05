import os
import requests
import time
import json
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from functools import wraps

# Configuración
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_compras.log')
    ]
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_123456')

# Configuración Telegram
TELEGRAM_CONFIG = {
    'bot_token': '',
    'chat_id': ''
}

# Usuario y contraseña para la web
USUARIO_ADMIN = 'admin'
PASSWORD_ADMIN = 'admin123'

# ========== SISTEMA PRINCIPAL ==========
class ConfiguracionUsuario:
    def __init__(self):
        self.datos_pago = {
            'nombre': '',
            'apellido': '',
            'direccion': '',
            'ciudad': '',
            'codigo_postal': '',
            'pais': 'España',
            'telefono': '',
            'email': ''
        }
        self.tarjeta = {'numero': '', 'mes_expiracion': '', 'anio_expiracion': '', 'cvv': '', 'titular': ''}
        self.paypal = {'email': '', 'password': ''}
        self.telegram = {'bot_token': '', 'chat_id': ''}

class SistemaBot:
    def __init__(self):
        self.config = ConfiguracionUsuario()
        self.preventas = []
        self.productos = []
        self.en_ejecucion = True
        self.logs = []
        self.cargar_configuracion()

    def cargar_configuracion(self):
        for archivo in ['config_usuario.json', 'preventas.json', 'productos.json']:
            if os.path.exists(archivo):
                try:
                    with open(archivo, 'r') as f:
                        data = json.load(f)
                        if archivo == 'config_usuario.json':
                            self.config.datos_pago.update(data.get('datos_pago', {}))
                            self.config.tarjeta.update(data.get('tarjeta', {}))
                            self.config.paypal.update(data.get('paypal', {}))
                            self.config.telegram.update(data.get('telegram', {}))
                            if self.config.telegram.get('bot_token'):
                                TELEGRAM_CONFIG['bot_token'] = self.config.telegram['bot_token']
                            if self.config.telegram.get('chat_id'):
                                TELEGRAM_CONFIG['chat_id'] = self.config.telegram['chat_id']
                        elif archivo == 'preventas.json':
                            self.preventas = data if isinstance(data, list) else data.get('preventas', [])
                        elif archivo == 'productos.json':
                            self.productos = data if isinstance(data, list) else data.get('productos', [])
                        self.add_log(f"✓ Cargado: {archivo}")
                except Exception:
                    pass

    def guardar_configuracion(self):
        config = {
            'datos_pago': self.config.datos_pago,
            'tarjeta': self.config.tarjeta,
            'paypal': self.config.paypal,
            'telegram': self.config.telegram
        }
        with open('config_usuario.json', 'w') as f:
            json.dump(config, f, indent=2)
        with open('preventas.json', 'w') as f:
            json.dump(self.preventas, f, indent=2)
        with open('productos.json', 'w') as f:
            json.dump(self.productos, f, indent=2)
        self.add_log("✓ Configuración guardada")

    def add_log(self, mensaje):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logs.append(f"[{timestamp}] {mensaje}")
        if len(self.logs) > 200:
            self.logs = self.logs[-200:]
        logging.info(mensaje)

    def enviar_notificacion(self, mensaje):
        try:
            token = TELEGRAM_CONFIG.get('bot_token') or self.config.telegram.get('bot_token')
            chat_id = TELEGRAM_CONFIG.get('chat_id') or self.config.telegram.get('chat_id')
            if token and chat_id:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, json={'chat_id': chat_id, 'text': mensaje, 'parse_mode': 'HTML'}, timeout=5)
                self.add_log("✓ Notificación enviada")
        except Exception as e:
            self.add_log(f"✗ Error notificación: {e}")

sistema = SistemaBot()

# ========== DECORADOR LOGIN ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== RUTAS ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == USUARIO_ADMIN and request.form.get('password') == PASSWORD_ADMIN:
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('Credenciales incorrectas', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html',
                         estado=sistema.en_ejecucion,
                         preventas=len(sistema.preventas),
                         productos=len(sistema.productos),
                         fecha=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/configuracion', methods=['GET', 'POST'])
@login_required
def configuracion():
    if request.method == 'POST':
        datos = request.form
        sistema.config.datos_pago['nombre'] = datos.get('nombre', '')
        sistema.config.datos_pago['apellido'] = datos.get('apellido', '')
        sistema.config.datos_pago['direccion'] = datos.get('direccion', '')
        sistema.config.datos_pago['ciudad'] = datos.get('ciudad', '')
        sistema.config.datos_pago['codigo_postal'] = datos.get('codigo_postal', '')
        sistema.config.datos_pago['telefono'] = datos.get('telefono', '')
        sistema.config.datos_pago['email'] = datos.get('email', '')
        sistema.config.datos_pago['pais'] = datos.get('pais', 'España')
        sistema.config.tarjeta['numero'] = datos.get('tarjeta_numero', '')
        sistema.config.tarjeta['mes_expiracion'] = datos.get('tarjeta_mes', '')
        sistema.config.tarjeta['anio_expiracion'] = datos.get('tarjeta_anio', '')
        sistema.config.tarjeta['cvv'] = datos.get('tarjeta_cvv', '')
        sistema.config.tarjeta['titular'] = datos.get('tarjeta_titular', '')
        sistema.config.paypal['email'] = datos.get('paypal_email', '')
        sistema.config.paypal['password'] = datos.get('paypal_password', '')
        sistema.config.telegram['bot_token'] = datos.get('telegram_token', '')
        sistema.config.telegram['chat_id'] = datos.get('telegram_chat_id', '')

        if sistema.config.telegram['bot_token']:
            TELEGRAM_CONFIG['bot_token'] = sistema.config.telegram['bot_token']
        if sistema.config.telegram['chat_id']:
            TELEGRAM_CONFIG['chat_id'] = sistema.config.telegram['chat_id']

        sistema.guardar_configuracion()
        flash('Configuración guardada', 'success')
        return redirect(url_for('configuracion'))

    return render_template('configuracion.html', config=sistema.config, telegram_config=TELEGRAM_CONFIG)

@app.route('/preventas')
@login_required
def preventas():
    return render_template('preventas.html', preventas=sistema.preventas)

@app.route('/productos')
@login_required
def productos():
    return render_template('productos.html', productos=sistema.productos)

# ========== API ==========
@app.route('/api/estado')
@login_required
def api_estado():
    return jsonify({
        'ejecutando': sistema.en_ejecucion,
        'preventas': len(sistema.preventas),
        'productos': len(sistema.productos)
    })

@app.route('/api/preventas/agregar', methods=['POST'])
@login_required
def api_agregar_preventa():
    data = request.json
    url = data.get('url', '').strip()
    cantidad = int(data.get('cantidad', 1))

    if not url or 'tcgfactory' not in url.lower():
        return jsonify({'success': False, 'error': 'URL no válida para preventas (debe ser de TCG Factory)'})

    for p in sistema.preventas:
        if p['url'] == url:
            return jsonify({'success': False, 'error': 'Ya existe'})

    sistema.preventas.append({'url': url, 'cantidad': cantidad, 'estado': 'pendiente', 'fecha': datetime.now().isoformat()})
    sistema.guardar_configuracion()
    sistema.add_log("✓ Preventa añadida")
    sistema.enviar_notificacion(f"📦 Nueva preventa: {url}")

    return jsonify({'success': True})

@app.route('/api/preventas/eliminar/<int:index>', methods=['DELETE'])
@login_required
def api_eliminar_preventa(index):
    if 0 <= index < len(sistema.preventas):
        sistema.preventas.pop(index)
        sistema.guardar_configuracion()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/productos/agregar', methods=['POST'])
@login_required
def api_agregar_producto():
    data = request.json
    nombre = data.get('nombre', '').strip()
    url = data.get('url', '').strip()

    if not nombre or not url:
        return jsonify({'success': False, 'error': 'Nombre y URL requeridos'})

    tienda = None
    url_lower = url.lower()
    if 'topps' in url_lower: 
        tienda = 'topps'
    elif 'game' in url_lower: 
        tienda = 'game'
    elif 'inside-the-box' in url_lower: 
        tienda = 'inside_box'
    else: 
        return jsonify({'success': False, 'error': 'URL no válida o tienda no compatible (.com o .es)'})

    for p in sistema.productos:
        if p['url'] == url:
            return jsonify({'success': False, 'error': 'Ya existe'})

    sistema.productos.append({
        'nombre': nombre, 'url': url, 'tienda': tienda,
        'disponible': False, 'notificado': False,
        'fecha': datetime.now().isoformat()
    })
    sistema.guardar_configuracion()
    sistema.add_log(f"✓ Producto añadido: {nombre}")
    sistema.enviar_notificacion(f"🔔 Nuevo producto: {nombre} ({tienda})")

    return jsonify({'success': True})

@app.route('/api/productos/eliminar/<int:index>', methods=['DELETE'])
@login_required
def api_eliminar_producto(index):
    if 0 <= index < len(sistema.productos):
        sistema.productos.pop(index)
        sistema.guardar_configuracion()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/productos/verificar', methods=['POST'])
@login_required
def api_verificar_productos():
    resultados = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
    }

    for p in sistema.productos:
        try:
            response = requests.get(p['url'], headers=headers, timeout=10)
            disponible = False
            if response.status_code == 200:
                text = response.text.lower()
                if p['tienda'] == 'topps': 
                    disponible = any(w in text for w in ['add to cart', 'añadir', 'comprar', 'stock', 'anadir'])
                elif p['tienda'] == 'game': 
                    disponible = any(w in text for w in ['add to basket', 'añadir a la cesta', 'comprar', 'anadir a la cesta'])
                elif p['tienda'] == 'inside_box': 
                    disponible = any(w in text for w in ['in den warenkorb', 'kaufen', 'verfügbar'])
            p['disponible'] = disponible
            resultados.append({'nombre': p['nombre'], 'disponible': disponible})
        except Exception:
            resultados.append({'nombre': p['nombre'], 'disponible': False})

    sistema.guardar_configuracion()
    return jsonify({'success': True, 'resultados': resultados})

@app.route('/api/preventas/verificar', methods=['POST'])
@login_required
def api_verificar_preventas():
    resultados = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    for p in sistema.preventas:
        try:
            response = requests.get(p['url'], timeout=10, headers=headers)
            disponible = any(word in response.text.lower() for word in ['preventa', 'reservar', 'añadir al carrito', 'anadir al carrito', 'comprar'])
            resultados.append({'url': p['url'][:50], 'disponible': disponible})
        except Exception:
            resultados.append({'url': p['url'][:50], 'disponible': False})
    return jsonify({'success': True, 'resultados': resultados})

@app.route('/api/logs')
@login_required
def api_logs():
    return jsonify({'logs': sistema.logs[-50:]})

@app.route('/api/notificar', methods=['POST'])
@login_required
def api_notificar():
    mensaje = request.json.get('mensaje', '🔔 Prueba desde el Bot')
    sistema.enviar_notificacion(mensaje)
    return jsonify({'success': True})

# ========== INICIO ==========
if __name__ == '__main__':
    if not os.path.exists('templates'):
        os.makedirs('templates')

    print("="*60)
    print("🤖 BOT DE COMPRAS AUTOMÁTICAS")
    print("="*60)
    print()
    print("🌐 Abre en tu navegador: http://localhost:5000")
    print("👤 Usuario: admin")
    print("🔑 Contraseña: admin123")
    print()
    print("="*60)

    app.run(host='0.0.0.0', port=5000, debug=True)