class LogisticaEnvioDTO:
    def __init__(self, alto, ancho, profundidad, peso_kg, requiere_fragil, tipo_empaque):
        self.alto = float(alto) if alto else 0.0
        self.ancho = float(ancho) if ancho else 0.0
        self.profundidad = float(profundidad) if profundidad else 0.0
        self.peso_kg = float(peso_kg) if peso_kg else 0.0
        self.requiere_fragil = bool(requiere_fragil)
        self.tipo_empaque = str(tipo_empaque)

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
        self.productoID = productoID
        self.categoria = categoria
        self.color = color
        self.logistica = logistica # Instancia de LogisticaEnvioDTO
        self.material = material
        self.nombre = nombre
        self.precio = float(precio) if precio else 0.0
        self.stock = int(stock) if stock else 0
        self.talla = talla
        self.vendedorID = vendedorID

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