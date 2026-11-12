# Entrecol - Sistema de Gestión Web (Flask + MVC)

Proyecto académico desarrollado para la Universidad Manuela Beltrán. Es un sistema web modular basado en el patrón **MVC (Modelo-Vista-Controlador)** construido en Python con Flask y MySQL, enfocado en la gestión de datos, seguridad con autenticación robusta y generación de reportes automáticos en PDF y gráficos.

## 👥 Integrantes
* **Juan Jiménez**
* **Cristian Vanegas**

---

## 🚀 Tecnologías Utilizadas
* **Lenguaje:** Python 3
* **Framework Web:** Flask
* **Base de Datos:** MySQL (`mysql-connector-python`)
* **Seguridad:** Bcrypt (cifrado de contraseñas) y validación por Captcha
* **Procesamiento de Archivos:** `openpyxl` (para lectura de Excel)
* **Reportes y Gráficos:** `matplotlib` (generación de gráficos) y `xhtml2pdf` (exportación a PDF en formato puro Python)

---

## 📁 Estructura del Proyecto
```text
entrecol/
├── app.py            # CONTROLADOR: rutas principales (login, CRUD, reportes)
├── modelos.py        # MODELO: consultas SQL parametrizadas
├── db.py             # Conexión a la base de datos MySQL
├── cargadores.py     # Procesamiento e inserción de archivos (Excel/JSON/DAT)
├── reportes.py       # Generación de gráficos y conversión a PDF
├── seguridad.py      # Gestión de contraseñas, captcha, roles y auditoría
├── templates/        # VISTA: plantillas HTML del sistema
├── db/
│   └── schema.sql    # Estructura del modelo relacional en SQL
├── data/             # Archivos de datos del sistema
├── requirements.txt  # Dependencias del proyecto
├── .env.example      # Variables de entorno de ejemplo
└── README.md         # Documentación del proyecto