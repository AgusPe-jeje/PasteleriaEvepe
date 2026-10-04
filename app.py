import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

ARCHIVO_DATOS = 'datos_pasteleria.json'

def cargar_datos():
    """Lee el archivo JSON del disco o crea la estructura vacía si no existe."""
    if os.path.exists(ARCHIVO_DATOS):
        with open(ARCHIVO_DATOS, 'r', encoding='utf-8') as f:
            datos = json.load(f)
            if 'ventas' not in datos:
                datos['ventas'] = []
            return datos
    return {
        'insumos': {},
        'recetas_guardadas': [],
        'boxes_guardados': [],
        'ventas': []
    }

def guardar_datos(datos):
    """Guarda en disco los cambios realizados en el diccionario."""
    with open(ARCHIVO_DATOS, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=4)

def redondear_precio(valor, paso=100):
    if valor <= 0:
        return 0
    return int(round(valor / paso) * paso)

def recalcular_recetas(datos):
    insumos = datos.get('insumos', {})
    for receta in datos.get('recetas_guardadas', []):
        c_ing = 0
        for item in receta.get('ingredientes', []):
            n_ing = item['nombre']
            cant = item['cantidad']
            if n_ing in insumos:
                d = insumos[n_ing]
                c_ing += (cant / d['paquete_cant']) * d['precio_compra']
        
        c_extras = c_ing * 0.15
        c_total = c_ing + c_extras
        ganancia_calculada = c_total * (receta.get('porcentaje', 80) / 100)
        
        precio_venta_bruto = c_total + ganancia_calculada
        precio_venta_redondeado = redondear_precio(precio_venta_bruto, paso=100)
        ganancia_real = precio_venta_redondeado - c_total
        
        receta['costo'] = int(c_total)
        receta['ganancia'] = int(ganancia_real)
        receta['precio_venta'] = precio_venta_redondeado

def recalcular_boxes(datos):
    insumos = datos.get('insumos', {})
    recetas = datos.get('recetas_guardadas', [])
    for box in datos.get('boxes_guardados', []):
        costo_total_box = 0
        porcentaje_box = box.get('porcentaje', 50)
        
        for prod in box.get('productos', []):
            receta_match = next((r for r in recetas if r['nombre'] == prod['nombre']), None)
            cant_unidades = prod['cantidad']
            
            if receta_match:
                costo_total_box += receta_match['costo'] * cant_unidades
            elif prod['nombre'] in insumos:
                d = insumos[prod['nombre']]
                costo_item = (cant_unidades / d['paquete_cant']) * d['precio_compra']
                costo_total_box += costo_item

        ganancia_calculada = costo_total_box * (porcentaje_box / 100)
        precio_venta_bruto = costo_total_box + ganancia_calculada
        
        precio_venta_redondeado = redondear_precio(precio_venta_bruto, paso=100)
        ganancia_real = precio_venta_redondeado - costo_total_box

        box['costo'] = int(costo_total_box)
        box['ganancia'] = int(ganancia_real)
        box['precio_venta'] = precio_venta_redondeado

@app.route('/', methods=['GET', 'POST'])
def inicio():
    datos = cargar_datos()
    insumos = datos['insumos']
    recetas_guardadas = datos['recetas_guardadas']
    boxes_guardados = datos['boxes_guardados']
    ventas = datos.get('ventas', [])

    costo_ingredientes = 0
    gastos_extras = 0
    costo_total = 0
    ganancia_mano_obra = 0
    precio_sugerido = 0
    nombre_receta = ""
    porcentaje_ganancia = 80
    ingredientes_actuales = []

    if request.method == 'POST':
        nombre_receta = request.form.get('nombre_receta', 'Receta sin nombre')
        nombres_usados = request.form.getlist('ingrediente_nombre[]')
        cantidades_usadas = request.form.getlist('ingrediente_cantidad[]')
        porcentaje_ganancia = float(request.form.get('porcentaje_ganancia') or 80)

        for nombre_raw, cant in zip(nombres_usados, cantidades_usadas):
            nombre = nombre_raw.split(' (en ')[0].strip() if ' (en ' in nombre_raw else nombre_raw.strip()
            
            if nombre in insumos and cant and float(cant) > 0:
                cantidad = float(cant)
                ingredientes_actuales.append({'nombre': nombre, 'cantidad': cantidad})
                datos_insumo = insumos[nombre]
                costo_item = (cantidad / datos_insumo['paquete_cant']) * datos_insumo['precio_compra']
                costo_ingredientes += costo_item

        gastos_extras = costo_ingredientes * 0.15
        costo_total = costo_ingredientes + gastos_extras
        ganancia_mano_obra_bruta = costo_total * (porcentaje_ganancia / 100)
        precio_sugerido_bruto = costo_total + ganancia_mano_obra_bruta
        
        precio_sugerido = redondear_precio(precio_sugerido_bruto, paso=100)
        ganancia_mano_obra = precio_sugerido - costo_total

        if 'accion_guardar' in request.form and nombre_receta.strip() and ingredientes_actuales:
            receta_existente = next((r for r in recetas_guardadas if r['nombre'].lower() == nombre_receta.strip().lower()), None)
            
            if receta_existente:
                receta_existente['ingredientes'] = ingredientes_actuales
                receta_existente['porcentaje'] = porcentaje_ganancia
            else:
                recetas_guardadas.append({
                    'nombre': nombre_receta.strip(),
                    'ingredientes': ingredientes_actuales,
                    'porcentaje': porcentaje_ganancia,
                    'costo': int(costo_total),
                    'precio_venta': int(precio_sugerido),
                    'ganancia': int(ganancia_mano_obra)
                })
            
            recalcular_recetas(datos)
            recalcular_boxes(datos)
            guardar_datos(datos)

    recalcular_recetas(datos)
    recalcular_boxes(datos)
    guardar_datos(datos)

    # FILTRADO DE VENTAS POR MES SELECCIONADO
    mes_actual_str = datetime.now().strftime('%Y-%m')
    mes_seleccionado = request.args.get('mes_filtro', mes_actual_str)

    ventas_filtradas = [v for v in ventas if v.get('fecha', '').startswith(mes_seleccionado)]

    # Cálculo de métricas financieras del mes seleccionado
    total_ingresos = sum(v['precio_total'] for v in ventas_filtradas)
    total_costos = sum(v['costo_total'] for v in ventas_filtradas)
    total_ganancia = sum(v['ganancia_total'] for v in ventas_filtradas)

    fecha_hoy = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'index.html',
        insumos=insumos,
        insumos_json=json.dumps(insumos),
        recetas_json=json.dumps(recetas_guardadas),
        boxes_json=json.dumps(boxes_guardados),
        costo_ingredientes=int(costo_ingredientes),
        gastos_extras=int(gastos_extras),
        costo_total=int(costo_total),
        ganancia_mano_obra=int(ganancia_mano_obra),
        precio_sugerido=int(precio_sugerido),
        porcentaje_ganancia=int(porcentaje_ganancia),
        recetas=recetas_guardadas,
        boxes=boxes_guardados,
        ventas=ventas_filtradas,
        total_ingresos=total_ingresos,
        total_costos=total_costos,
        total_ganancia=total_ganancia,
        fecha_hoy=fecha_hoy,
        mes_seleccionado=mes_seleccionado,
        nombre_receta=nombre_receta,
        ingredientes_actuales=ingredientes_actuales
    )

@app.route('/nueva_venta', methods=['POST'])
def nueva_venta():
    datos = cargar_datos()
    recetas = datos['recetas_guardadas']
    boxes = datos['boxes_guardados']

    producto_raw = request.form.get('producto_nombre', '').strip()
    cantidad = int(request.form.get('cantidad', 1) or 1)
    fecha = request.form.get('fecha', datetime.now().strftime('%Y-%m-%d'))

    producto_nombre = producto_raw.split(' (')[0].strip() if ' (' in producto_raw else producto_raw

    receta_match = next((r for r in recetas if r['nombre'].lower() == producto_nombre.lower()), None)
    box_match = next((b for b in boxes if b['nombre'].lower() == producto_nombre.lower()), None)

    if (receta_match or box_match) and cantidad > 0:
        item = receta_match if receta_match else box_match
        tipo = 'Receta' if receta_match else 'Box'

        costo_unitario = item['costo']
        precio_unitario = item['precio_venta']
        ganancia_unitaria = item['ganancia']

        nueva_v = {
            'producto': item['nombre'],
            'tipo': tipo,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'precio_total': precio_unitario * cantidad,
            'costo_total': costo_unitario * cantidad,
            'ganancia_total': ganancia_unitaria * cantidad,
            'fecha': fecha
        }
        
        datos['ventas'].insert(0, nueva_v)
        guardar_datos(datos)

    mes_venta = fecha[:7] if len(fecha) >= 7 else datetime.now().strftime('%Y-%m')
    return redirect(url_for('inicio', paso=5, mes_filtro=mes_venta))

@app.route('/eliminar_venta/<int:index>', methods=['POST'])
def eliminar_venta(index):
    datos = cargar_datos()
    mes_filtro = request.args.get('mes_filtro', datetime.now().strftime('%Y-%m'))
    if 0 <= index < len(datos.get('ventas', [])):
        datos['ventas'].pop(index)
        guardar_datos(datos)
    return redirect(url_for('inicio', paso=5, mes_filtro=mes_filtro))

@app.route('/nuevo_box', methods=['POST'])
def nuevo_box():
    datos = cargar_datos()
    boxes_guardados = datos['boxes_guardados']

    nombre_box = request.form.get('nombre_box', 'Box Desayuno').strip()
    prod_nombres = request.form.getlist('box_prod_nombre[]')
    prod_cantidades = request.form.getlist('box_prod_cantidad[]')
    porcentaje_box = float(request.form.get('porcentaje_ganancia_box') or 50)

    productos = []
    for p_nom, p_cant in zip(prod_nombres, prod_cantidades):
        p_clean = p_nom.split(' (')[0].strip() if ' (' in p_nom else p_nom.strip()
        if p_clean and p_cant and float(p_cant) > 0:
            productos.append({'nombre': p_clean, 'cantidad': float(p_cant)})

    if nombre_box and productos:
        existente = next((b for b in boxes_guardados if b['nombre'].lower() == nombre_box.lower()), None)
        if existente:
            existente['productos'] = productos
            existente['porcentaje'] = porcentaje_box
        else:
            boxes_guardados.append({
                'nombre': nombre_box,
                'productos': productos,
                'porcentaje': porcentaje_box,
                'costo': 0,
                'precio_venta': 0,
                'ganancia': 0
            })
        recalcular_boxes(datos)
        guardar_datos(datos)

    return redirect(url_for('inicio', paso=4))

@app.route('/eliminar_box/<int:index>', methods=['POST'])
def eliminar_box(index):
    datos = cargar_datos()
    if 0 <= index < len(datos['boxes_guardados']):
        datos['boxes_guardados'].pop(index)
        guardar_datos(datos)
    return redirect(url_for('inicio', paso=4))

@app.route('/nuevo_insumo', methods=['POST'])
def nuevo_insumo():
    datos = cargar_datos()
    nombre = request.form.get('nuevo_nombre')
    precio = request.form.get('nuevo_precio')
    cantidad = request.form.get('nueva_cantidad')
    unidad = request.form.get('nueva_unidad', 'gr')

    if nombre and precio and cantidad:
        p_val = float(precio)
        c_val = float(cantidad)
        datos['insumos'][nombre.strip().title()] = {
            'precio_compra': int(p_val) if p_val.is_integer() else p_val,
            'paquete_cant': int(c_val) if c_val.is_integer() else c_val,
            'unidad': unidad
        }
        guardar_datos(datos)
    return redirect(url_for('inicio'))

@app.route('/editar_insumo', methods=['POST'])
def editar_insumo():
    datos = cargar_datos()
    nombre = request.form.get('nombre_insumo')
    nuevo_precio = request.form.get('precio_compra')
    nueva_cantidad = request.form.get('paquete_cant')

    if nombre in datos['insumos'] and nuevo_precio and nueva_cantidad:
        p_val = float(nuevo_precio)
        c_val = float(nueva_cantidad)
        datos['insumos'][nombre]['precio_compra'] = int(p_val) if p_val.is_integer() else p_val
        datos['insumos'][nombre]['paquete_cant'] = int(c_val) if c_val.is_integer() else c_val
        guardar_datos(datos)
    return redirect(url_for('inicio'))

@app.route('/eliminar_insumo/<nombre>', methods=['POST'])
def eliminar_insumo(nombre):
    datos = cargar_datos()
    if nombre in datos['insumos']:
        del datos['insumos'][nombre]
        guardar_datos(datos)
    return redirect(url_for('inicio'))

@app.route('/eliminar_receta/<int:index>', methods=['POST'])
def eliminar_receta(index):
    datos = cargar_datos()
    if 0 <= index < len(datos['recetas_guardadas']):
        datos['recetas_guardadas'].pop(index)
        guardar_datos(datos)
    return redirect(url_for('inicio', paso=4))

if __name__ == '__main__':
    app.run(debug=True)