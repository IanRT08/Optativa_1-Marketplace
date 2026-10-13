import re

# SEGURIDAD: Patron para productoID — debe tener letras, numeros y guion. Ej: PROD-001
PATRON_ID = re.compile(r'^[A-Za-z]{1,20}-[A-Za-z0-9]{1,20}$')

# SEGURIDAD: Patron para campos de texto — debe contener al menos una letra
# y no tener mas de 2 caracteres especiales consecutivos.
PATRON_TEXTO = re.compile(r'[A-Za-zÁÉÍÓÚáéíóúÑñÜü]')
PATRON_ESPECIALES_SEGUIDOS = re.compile(r'[^A-Za-z0-9ÁÉÍÓÚáéíóúÑñÜü\s]{3,}')


def _limpiar(valor, max_len, requerido=False):
    """
    SEGURIDAD: Limpia y normaliza un campo de texto.
    - strip() elimina espacios al inicio y al final.
    - re.sub colapsa espacios multiples internos en uno solo.
    - Si el campo es requerido y queda vacio, lanza un error.
    - Trunca al maximo de caracteres permitido.
    """
    if not valor:
        if requerido:
            raise ValueError("Campo requerido no puede estar vacio.")
        return ''
    limpio = re.sub(r'\s+', ' ', str(valor).strip())
    if requerido and not limpio:
        raise ValueError("Campo requerido no puede contener solo espacios.")
    return limpio[:max_len]


def _validar_texto(valor, nombre_campo):
    """
    SEGURIDAD: Valida que un campo de texto:
    - Contenga al menos una letra (evita cadenas como '123', '[!.-}').
    - No tenga mas de 2 caracteres especiales consecutivos.
    """
    if not valor:
        return
    if not PATRON_TEXTO.search(valor):
        raise ValueError(f"{nombre_campo} debe contener al menos una letra.")
    if PATRON_ESPECIALES_SEGUIDOS.search(valor):
        raise ValueError(f"{nombre_campo} no puede tener mas de 2 caracteres especiales seguidos.")


def _validar_id(valor):
    """
    SEGURIDAD: Valida que el productoID tenga el formato LETRAS-ALFANUMERICO.
    Ejemplos validos: PROD-001, CEL-A12, ROPA-99
    """
    if not PATRON_ID.match(valor):
        raise ValueError("El ID debe tener el formato LETRAS-ALFANUMERICO (ej: PROD-001).")


class LogisticaEnvioDTO:
    def __init__(self, alto, ancho, profundidad, peso_kg, requiere_fragil, tipo_empaque):
        # SEGURIDAD: Se valida que los valores numericos sean positivos para evitar datos invalidos.
        self.alto = max(0.0, float(alto)) if alto else 0.0
        self.ancho = max(0.0, float(ancho)) if ancho else 0.0
        self.profundidad = max(0.0, float(profundidad)) if profundidad else 0.0
        self.peso_kg = max(0.0, float(peso_kg)) if peso_kg else 0.0
        self.requiere_fragil = bool(requiere_fragil)
        tipo = _limpiar(tipo_empaque, 100)
        _validar_texto(tipo, "Tipo de empaque")
        self.tipo_empaque = tipo

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
        # SEGURIDAD: _limpiar() hace strip() y colapsa espacios multiples.
        # _validar_id() exige formato LETRAS-ALFANUMERICO (ej: PROD-001).
        pid = _limpiar(productoID, 50, requerido=True)
        _validar_id(pid)
        self.productoID = pid

        nombre_ = _limpiar(nombre, 200, requerido=True)
        _validar_texto(nombre_, "Nombre")
        self.nombre = nombre_

        cat = _limpiar(categoria, 100, requerido=True)
        _validar_texto(cat, "Categoria")
        self.categoria = cat

        # SEGURIDAD: Color puede venir del dropdown (valor predefinido) o campo personalizado.
        # En ambos casos se limpia y valida igual.
        color_ = _limpiar(color, 50)
        _validar_texto(color_, "Color")
        self.color = color_

        mat = _limpiar(material, 100)
        _validar_texto(mat, "Material")
        self.material = mat

        talla_ = _limpiar(talla, 50)
        _validar_texto(talla_, "Talla")
        self.talla = talla_

        vid = _limpiar(vendedorID, 50)
        _validar_texto(vid, "Vendedor ID")
        self.vendedorID = vid

        self.logistica = logistica  # Instancia de LogisticaEnvioDTO

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
