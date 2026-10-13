import re

def _limpiar(valor, max_len, requerido=False):
    """
    SEGURIDAD: Limpia y normaliza un campo de texto.
    - strip() elimina espacios al inicio y al final.
    - re.sub colapsa espacios multiples internos en uno solo (ej: 'Celular    Gris' -> 'Celular Gris').
    - Si el campo es requerido y queda vacio, lanza un error.
    - Trunca al maximo de caracteres permitido.
    """
    if not valor:
        if requerido:
            raise ValueError(f"Campo requerido no puede estar vacio.")
        return ''
    limpio = re.sub(r'\s+', ' ', str(valor).strip())
    if requerido and not limpio:
        raise ValueError(f"Campo requerido no puede contener solo espacios.")
    return limpio[:max_len]


class LogisticaEnvioDTO:
    def __init__(self, alto, ancho, profundidad, peso_kg, requiere_fragil, tipo_empaque):
        # SEGURIDAD: Se valida que los valores numericos sean positivos para evitar datos invalidos.
        self.alto = max(0.0, float(alto)) if alto else 0.0
        self.ancho = max(0.0, float(ancho)) if ancho else 0.0
        self.profundidad = max(0.0, float(profundidad)) if profundidad else 0.0
        self.peso_kg = max(0.0, float(peso_kg)) if peso_kg else 0.0
        self.requiere_fragil = bool(requiere_fragil)
        # SEGURIDAD: Se limita longitud y se normalizan espacios.
        self.tipo_empaque = _limpiar(tipo_empaque, 100)

    def to_dict(self):
        return {
            "DimensionesCm": {
                "Alto": self.alto,
                "Ancho": self.ancho,
                "Profundidad": self.profundidad
            },
            "PesoKg": self.peso_kg,
            "RequiereFragil": self.requiere_fragil,
            "TipoEmpaque": self.tipo_empaque
        }


class ProductoDTO:
    def __init__(self, productoID, categoria, color, logistica, material, nombre, precio, stock, talla, vendedorID):
        # SEGURIDAD: _limpiar() hace strip(), colapsa espacios multiples y valida campos requeridos.
        self.productoID = _limpiar(productoID, 50, requerido=True)
        self.nombre = _limpiar(nombre, 200, requerido=True)
        self.categoria = _limpiar(categoria, 100, requerido=True)
        self.color = _limpiar(color, 50)
        self.logistica = logistica  # Instancia de LogisticaEnvioDTO
        self.material = _limpiar(material, 100)
        self.talla = _limpiar(talla, 50)
        self.vendedorID = _limpiar(vendedorID, 50)
        # SEGURIDAD: Se valida que precio y stock no sean negativos.
        self.precio = max(0.0, float(precio)) if precio else 0.0
        # SOLUCION: Convertimos primero a float para soportar '100.0' y luego a int
        self.stock = max(0, int(float(stock))) if stock else 0

    def to_dict(self):
        logistica_dict = self.logistica.to_dict() if isinstance(self.logistica, LogisticaEnvioDTO) else self.logistica
        return {
            "productoID": self.productoID,
            "Categoria": self.categoria,
            "Color": self.color,
            "LogisticaEnvio": logistica_dict,
            "Material": self.material,
            "Nombre": self.nombre,
            "Precio": self.precio,
            "Stock": self.stock,
            "Talla": self.talla,
            "VendedorID": self.vendedorID
        }
