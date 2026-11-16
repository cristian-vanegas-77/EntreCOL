"""REPORTES: Genera gráficas en Base64 con Matplotlib y convierte plantillas HTML a PDF con xhtml2pdf."""
import io
import base64
import matplotlib
matplotlib.use("Agg")  # Evita errores de interfaz gráfica en servidores web
import matplotlib.pyplot as plt
from xhtml2pdf import pisa


def generar_grafica_barras(etiquetas, valores, titulo, xlabel="", ylabel=""):
    """Dibuja un gráfico de barras y devuelve la imagen codificada en Base64 para incrustar en HTML."""
    fig, ax = plt.subplots(figsize=(7, 3.8))

    if not etiquetas or not valores:
        ax.text(0.5, 0.5, "Sin datos disponibles para graficar", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        ax.bar(etiquetas, valores, color="#2563eb", edgecolor="#1e40af")
        ax.set_title(titulo, fontsize=12, fontweight="bold", pad=12)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        plt.xticks(rotation=30, ha="right", fontsize=8)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)  # Libera memoria
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def generar_grafica_torta(etiquetas, valores, titulo):
    """Dibuja un gráfico circular (pie chart) y devuelve la imagen en Base64."""
    fig, ax = plt.subplots(figsize=(6, 4))

    if not etiquetas or not valores or sum(valores) == 0:
        ax.text(0.5, 0.5, "Sin datos disponibles para graficar", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        ax.pie(valores, labels=etiquetas, autopct="%1.1f%%", startangle=140, textprops={"fontsize": 8})
        ax.set_title(titulo, fontsize=12, fontweight="bold")

    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def generar_grafica_barras_comparativas(
    filas, clave_grupo, clave_subgrupo, clave_valor, titulo, xlabel="", ylabel=""
):
    """Dibuja un gráfico de barras agrupadas/comparativas y devuelve la imagen en Base64."""
    fig, ax = plt.subplots(figsize=(8, 4.2))

    if not filas:
        ax.text(0.5, 0.5, "Sin datos disponibles para graficar", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        grupos = sorted({str(f[clave_grupo]) for f in filas})
        subgrupos = sorted({str(f[clave_subgrupo]) for f in filas})

        matriz = {sg: [0] * len(grupos) for sg in subgrupos}
        for f in filas:
            idx_g = grupos.index(str(f[clave_grupo]))
            sg = str(f[clave_subgrupo])
            matriz[sg][idx_g] += float(f.get(clave_valor, 0))

        x = list(range(len(grupos)))
        ancho = 0.8 / max(len(subgrupos), 1)

        for i, sg in enumerate(subgrupos):
            posiciones = [xi + (i - (len(subgrupos) - 1) / 2) * ancho for xi in x]
            ax.bar(posiciones, matriz[sg], width=ancho, label=sg)

        ax.set_title(titulo, fontsize=11, fontweight="bold", pad=12)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(grupos, rotation=25, ha="right", fontsize=8)
        if len(subgrupos) <= 12:
            ax.legend(fontsize=7, ncol=2)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=120)
    plt.close(fig)
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


def html_a_pdf(html_renderizado):
    """Convierte una cadena HTML en bytes de PDF. Devuelve los bytes o None si falla."""
    pdf_buffer = io.BytesIO()
    estado = pisa.CreatePDF(io.StringIO(html_renderizado), dest=pdf_buffer)
    if estado.err:
        return None
    pdf_buffer.seek(0)
    return pdf_buffer.read()