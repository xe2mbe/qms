from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageTemplate, Frame, BaseDocTemplate, NextPageTemplate
from reportlab.lib.colors import HexColor
from datetime import datetime
import pandas as pd
import io
import os
import pytz

class FMREExporter:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        # Colores institucionales FMRE
        self.colors = {
            'fmre_green': HexColor('#2E7D32'),
            'fmre_blue': HexColor('#1565C0'), 
            'fmre_gray': HexColor('#424242'),
            'light_gray': HexColor('#F5F5F5'),
            'white': colors.white,
            'black': colors.black
        }
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Configura estilos personalizados para el reporte"""
        # Título principal
        self.styles.add(ParagraphStyle(
            name='FMRETitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            fontName='Helvetica-Bold',
            textColor=self.colors['fmre_green'],
            spaceAfter=20,
            alignment=1  # Center
        ))
        
        # Subtítulos
        self.styles.add(ParagraphStyle(
            name='FMRESubtitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=self.colors['fmre_blue'],
            spaceAfter=12,
            spaceBefore=8
        ))
        
        # Texto de estadísticas
        self.styles.add(ParagraphStyle(
            name='StatText',
            parent=self.styles['Normal'],
            fontSize=11,
            fontName='Helvetica',
            textColor=self.colors['fmre_gray'],
            spaceAfter=6
        ))
        
        # Encabezado institucional
        self.styles.add(ParagraphStyle(
            name='InstitutionalHeader',
            parent=self.styles['Normal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=self.colors['fmre_green'],
            alignment=0,
            spaceAfter=3
        ))
        
    def export_to_csv(self, df, filename=None):
        """Exporta DataFrame a CSV"""
        if filename is None:
            # Usar zona horaria de México
            mexico_tz = pytz.timezone('America/Mexico_City')
            now_mx = datetime.now(mexico_tz)
            filename = f"reportes_fmre_{now_mx.strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Preparar datos para CSV
        export_df = df.copy()
        if 'timestamp' in export_df.columns:
            export_df['timestamp'] = pd.to_datetime(export_df['timestamp']).dt.strftime('%d/%m/%Y %H:%M:%S')
        
        csv_buffer = io.StringIO()
        export_df.to_csv(csv_buffer, index=False, encoding='utf-8')
        return csv_buffer.getvalue(), filename
    
    def export_to_excel(self, df, filename=None):
        """Exporta DataFrame a Excel"""
        if filename is None:
            # Usar zona horaria de México
            mexico_tz = pytz.timezone('America/Mexico_City')
            now_mx = datetime.now(mexico_tz)
            filename = f"reportes_fmre_{now_mx.strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        excel_buffer = io.BytesIO()
        
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            # Hoja principal con reportes
            export_df = df.copy()
            if 'timestamp' in export_df.columns:
                export_df['timestamp'] = pd.to_datetime(export_df['timestamp'])
            
            # Reordenar columnas para mejor presentación incluyendo campos HF
            column_order = ['call_sign', 'operator_name', 'qth', 'ciudad', 'zona', 'sistema', 'hf_frequency', 'hf_mode', 'hf_power', 'signal_report', 'grid_locator', 'observations', 'timestamp']
            existing_columns = [col for col in column_order if col in export_df.columns]
            export_df = export_df[existing_columns]
            
            export_df.to_excel(writer, sheet_name='Reportes', index=False)
            
            # Formatear columnas
            worksheet = writer.sheets['Reportes']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        excel_buffer.seek(0)
        return excel_buffer.getvalue(), filename
    
    def export_to_pdf(self, df, stats=None, filename=None, session_date=None, current_user=None):
        """Exporta DataFrame y estadísticas a PDF"""
        if filename is None:
            # Usar zona horaria de México
            mexico_tz = pytz.timezone('America/Mexico_City')
            now_mx = datetime.now(mexico_tz)
            filename = f"reporte_fmre_{now_mx.strftime('%Y%m%d_%H%M%S')}.pdf"
        
        pdf_buffer = io.BytesIO()
        story = []
        
        # Agregar encabezado profesional
        self._add_professional_header(story, session_date, current_user)
        
        # Estadísticas si están disponibles
        if stats:
            story.append(Paragraph("📊 Resumen Estadístico", self.styles['FMRESubtitle']))
            story.append(Spacer(1, 10))
            
            # Crear cajas de estadísticas destacadas
            stats_boxes = self._create_stats_boxes(stats)
            story.append(stats_boxes)
            story.append(Spacer(1, 15))
            
            # Continuar con estadísticas detalladas
            self._continue_stats_section(story, stats, df, session_date, current_user)
            
        # Estadísticas generales en tabla mejorada (solo si hay stats)
        if stats:
            general_data = [
                ['📈 Total de Participantes', str(stats.get('total_participants', 0))],
                ['📋 Total de Reportes', str(stats.get('total_reports', 0))],
            ]
            
            general_table = Table(general_data, colWidths=[3*inch, 1.5*inch])
            general_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), self.colors['light_gray']),
                ('TEXTCOLOR', (0, 0), (-1, -1), self.colors['fmre_gray']),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('BOX', (0, 0), (-1, -1), 1, self.colors['fmre_blue']),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            
            story.append(general_table)
            story.append(Spacer(1, 15))
        
        # Marcar si hay reportes para numeración de páginas
        self._has_reports = not df.empty
        
        # Agregar tabla de reportes
        self._add_reports_table(story, df, session_date, current_user)
        
        # Construir PDF con orientaciones mixtas
        doc = self._create_mixed_orientation_doc(pdf_buffer)
        doc.build(story)
        
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue(), filename
    
    def _create_stats_boxes(self, stats):
        """Crea cajas destacadas para estadísticas principales"""
        # Obtener datos principales
        top_zona = stats.get('top_zona', {})
        top_sistema = stats.get('top_sistema', {})
        top_indicativo = stats.get('top_call_sign', {})  # Corregir clave
        
        # Crear datos para la tabla de cajas
        boxes_data = [
            [
                f"🏆 Zona Más Reportada\n{top_zona.get('zona', 'N/A')}\n({top_zona.get('count', 0)} reportes)",
                f"📡 Sistema Más Usado\n{top_sistema.get('sistema', 'N/A')}\n({top_sistema.get('count', 0)} reportes)",
                f"📻 Indicativo Más Activo\n{top_indicativo.get('call_sign', 'N/A')}\n({top_indicativo.get('count', 0)} reportes)"
            ]
        ]
        
        # Crear tabla de cajas
        boxes_table = Table(boxes_data, colWidths=[2.5*inch, 2.5*inch, 2.5*inch])
        boxes_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.colors['fmre_green']),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.colors['white']),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, self.colors['fmre_blue']),
            ('GRID', (0, 0), (-1, -1), 1, self.colors['white']),
        ]))
        
        return boxes_table
    
    def _continue_stats_section(self, story, stats, df, session_date=None, current_user=None):
        """Continúa con las estadísticas detalladas después de las cajas"""
        # Estadísticas por zona
        if 'by_zona' in stats and not stats['by_zona'].empty:
            story.append(Paragraph("🌍 Participantes por Zona", self.styles['FMRESubtitle']))
            zona_data = []
            for _, row in stats['by_zona'].iterrows():
                zona_data.append([f"Zona {row['zona']}", str(row['count'])])
            
            zona_table = Table(zona_data, colWidths=[2*inch, 1*inch])
            zona_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.colors['fmre_blue']),
                ('TEXTCOLOR', (0, 0), (-1, 0), self.colors['white']),
                ('BACKGROUND', (0, 1), (-1, -1), self.colors['light_gray']),
                ('TEXTCOLOR', (0, 1), (-1, -1), self.colors['fmre_gray']),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('BOX', (0, 0), (-1, -1), 1, self.colors['fmre_blue']),
                ('GRID', (0, 0), (-1, -1), 0.5, self.colors['fmre_blue'])
            ]))
            
            story.append(zona_table)
            story.append(Spacer(1, 15))
        
        # Estadísticas por sistema
        if 'by_sistema' in stats and not stats['by_sistema'].empty:
            story.append(Paragraph("📡 Participantes por Sistema", self.styles['FMRESubtitle']))
            sistema_data = []
            for _, row in stats['by_sistema'].iterrows():
                sistema_data.append([f"{row['sistema']}", str(row['count'])])
            
            sistema_table = Table(sistema_data, colWidths=[2*inch, 1*inch])
            sistema_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.colors['fmre_green']),
                ('TEXTCOLOR', (0, 0), (-1, 0), self.colors['white']),
                ('BACKGROUND', (0, 1), (-1, -1), self.colors['light_gray']),
                ('TEXTCOLOR', (0, 1), (-1, -1), self.colors['fmre_gray']),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('BOX', (0, 0), (-1, -1), 1, self.colors['fmre_green']),
                ('GRID', (0, 0), (-1, -1), 0.5, self.colors['fmre_green'])
            ]))
            
            story.append(sistema_table)
            story.append(Spacer(1, 20))
    
    def _add_reports_table(self, story, df, session_date=None, current_user=None):
        """Agrega la tabla de reportes al story"""
        # Salto de página para tabla de reportes en orientación horizontal
        if not df.empty:
            from reportlab.platypus.doctemplate import NextPageTemplate
            
            story.append(NextPageTemplate('landscape'))
            story.append(PageBreak())
            
            # Crear nueva página horizontal con encabezado profesional
            self._add_professional_header(story, session_date, current_user)
            
            story.append(Paragraph("📋 Anexo: Tabla Detalle", self.styles['FMRESubtitle']))
            story.append(Spacer(1, 12))
            
            # Preparar datos para la tabla con campos HF y numeración
            headers = ['#', 'Indicativo', 'Operador', 'Estado', 'Ciudad', 'Zona', 'Sistema', 'Frecuencia', 'Modo', 'Potencia', 'Señal', 'Grid', 'Observaciones', 'Fecha/Hora']
            export_data = [headers]  # Agregar encabezados
            
            for idx, (_, row) in enumerate(df.iterrows(), 1):
                export_data.append([
                    str(idx),  # Número consecutivo
                    row['call_sign'],
                    row['operator_name'],
                    row.get('region', 'N/A'),
                    row.get('ciudad', 'N/A'),
                    row['zona'],
                    row['sistema'],
                    row.get('hf_frequency', '-') or '-',
                    row.get('hf_mode', '-') or '-',
                    row.get('hf_power', '-') or '-',
                    row['signal_report'],
                    row.get('grid_locator', 'N/A') or 'N/A',
                    row['observations'] or '-',
                    pd.to_datetime(row['timestamp']).strftime('%d/%m/%Y %H:%M')
                ])
            
            # Crear tabla con estilo profesional y colores alternados - ajustada para landscape
            # Anchos de columna optimizados para orientación horizontal - ajustados para nombres largos
            col_widths = [0.3*inch, 0.7*inch, 1.8*inch, 0.5*inch, 1.2*inch, 0.4*inch, 0.5*inch, 
                         0.6*inch, 0.4*inch, 0.4*inch, 0.5*inch, 0.6*inch, 1.2*inch, 0.9*inch]
            table = Table(export_data, repeatRows=1, colWidths=col_widths)
            
            # Calcular número de filas para colores alternados
            num_rows = len(export_data)
            
            # Estilo base de la tabla
            table_style = [
                # Encabezado
                ('BACKGROUND', (0, 0), (-1, 0), self.colors['fmre_green']),
                ('TEXTCOLOR', (0, 0), (-1, 0), self.colors['white']),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                
                # Contenido general
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 7),  # Reducir tamaño de fuente
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),  # Reducir padding
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),  # Reducir padding lateral
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),  # Alineación vertical
                ('WORDWRAP', (0, 1), (-1, -1), True),  # Permitir word wrap
                
                # Bordes
                ('BOX', (0, 0), (-1, -1), 1, self.colors['fmre_green']),
                ('GRID', (0, 0), (-1, -1), 0.5, self.colors['fmre_gray']),
                
                # Resaltar columna de numeración
                ('BACKGROUND', (0, 1), (0, -1), self.colors['fmre_blue']),
                ('TEXTCOLOR', (0, 1), (0, -1), self.colors['white']),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ]
            
            # Agregar colores alternados para las filas
            for i in range(1, num_rows):
                if i % 2 == 0:  # Filas pares
                    table_style.append(('BACKGROUND', (1, i), (-1, i), self.colors['light_gray']))
                    table_style.append(('TEXTCOLOR', (1, i), (-1, i), self.colors['fmre_gray']))
            
            # Resaltar campos HF cuando están presentes
            for i in range(1, num_rows):
                # Si hay frecuencia HF, resaltar esas columnas
                if len(export_data[i]) > 7 and export_data[i][7] != '-':
                    table_style.extend([
                        ('BACKGROUND', (7, i), (9, i), HexColor('#E8F5E8')),  # Verde claro para HF
                        ('TEXTCOLOR', (7, i), (9, i), self.colors['fmre_green']),
                        ('FONTNAME', (7, i), (9, i), 'Helvetica-Bold'),
                    ])
            
            table.setStyle(TableStyle(table_style))
            
            story.append(table)
            story.append(Spacer(1, 20))
    
    def _add_footer(self, story):
        """Agrega pie de página profesional"""
        from reportlab.platypus import HRFlowable
        
        # Línea separadora
        story.append(HRFlowable(width="100%", thickness=0.5, lineCap='round', color=self.colors['fmre_gray']))
        story.append(Spacer(1, 10))
        
        # Texto del pie
        # Usar zona horaria de México para el pie de página
        mexico_tz = pytz.timezone('America/Mexico_City')
        now_mx = datetime.now(mexico_tz)
        
        footer_text = f"""
        <font color="#424242" size="8">
        <b>Federación Mexicana de Radioexperimentadores A.C.</b> | 
        Generado el {now_mx.strftime('%d/%m/%Y %H:%M:%S')} | 
        Sistema Integral de Gestión de QSOs (SIGQ)
        </font>
        """
        
        footer_para = Paragraph(footer_text, self.styles['Normal'])
        story.append(footer_para)
    
    def _create_mixed_orientation_doc(self, buffer):
        """Crea documento con orientaciones mixtas"""
        from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
        from reportlab.platypus.frames import Frame
        
        class MixedOrientationDoc(BaseDocTemplate):
            def __init__(self, filename, exporter_instance=None, **kwargs):
                BaseDocTemplate.__init__(self, filename, **kwargs)
                self.exporter = exporter_instance
                
                # Template para página vertical (primera página) - margen superior muy reducido
                portrait_frame = Frame(0.75*inch, 0.75*inch, 
                                     letter[0] - 1.5*inch, letter[1] - 1.0*inch,
                                     topPadding=0.1*inch)
                portrait_template = PageTemplate(id='portrait', frames=[portrait_frame],
                                               onPage=self._add_page_number)
                
                # Template para página horizontal (segunda página)
                landscape_frame = Frame(0.75*inch, 0.75*inch,
                                      landscape(letter)[0] - 1.5*inch, 
                                      landscape(letter)[1] - 1.5*inch)
                landscape_template = PageTemplate(id='landscape', frames=[landscape_frame], 
                                                pagesize=landscape(letter),
                                                onPage=self._add_page_number)
                
                self.addPageTemplates([portrait_template, landscape_template])
            
            def _add_page_number(self, canvas, doc):
                """Agrega numeración de páginas al pie"""
                canvas.saveState()
                
                # Obtener número de página actual
                page_num = canvas.getPageNumber()
                
                # Solo 1 página si no hay reportes, 2 si hay reportes
                total_pages = 1 if not (hasattr(self.exporter, '_has_reports') and self.exporter._has_reports) else 2
                
                # Posición del número de página (centrado en la parte inferior)
                canvas.setFont('Helvetica', 8)
                canvas.setFillColor(colors.gray)
                
                # Calcular posición centrada
                page_width = canvas._pagesize[0]
                page_text = f"Página {page_num} de {total_pages}"
                text_width = canvas.stringWidth(page_text, 'Helvetica', 8)
                x_position = (page_width - text_width) / 2
                
                canvas.drawString(x_position, 0.5*inch, page_text)
                canvas.restoreState()
        
        return MixedOrientationDoc(buffer, exporter_instance=self)
    
    
    def _add_professional_header(self, story, session_date=None, current_user=None):
        """Agrega encabezado profesional con logo y información institucional"""
        from reportlab.platypus import KeepTogether
        
        # Crear tabla para el encabezado con logo y texto
        header_data = []
        
        # Logo en tamaño original
        logo_path = "assets/LogoFMRE_medium.png"
        logo_cell = ""
        if os.path.exists(logo_path):
            logo = Image(logo_path)  # Sin forzar dimensiones
            logo_cell = logo
        
        # Información institucional
        org_style = ParagraphStyle(
            'OrgStyle',
            parent=self.styles['Normal'],
            fontSize=14,
            fontName='Helvetica-Bold',
            alignment=0,  # Left
            spaceAfter=3
        )
        
        report_style = ParagraphStyle(
            'ReportStyle',
            parent=self.styles['Normal'],
            fontSize=12,
            fontName='Helvetica',
            alignment=0,  # Left
            spaceAfter=2
        )
        
        date_style = ParagraphStyle(
            'DateStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica',
            alignment=0,  # Left
            spaceAfter=1
        )
        
        # Formatear fechas y usuario
        report_date = session_date.strftime('%d/%m/%Y') if session_date else datetime.now().strftime('%d/%m/%Y')
        generation_date = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        
        # Obtener nombre real del usuario con debug
        user_name = 'Sistema'  # Default
        if current_user:
            if isinstance(current_user, dict):
                user_name = current_user.get('full_name', '') or current_user.get('username', 'Sistema')
            elif hasattr(current_user, 'get'):
                user_name = current_user.get('full_name', '') or current_user.get('username', 'Sistema')
            else:
                # Si current_user no es dict ni tiene get, intentar acceso directo
                try:
                    user_name = getattr(current_user, 'full_name', '') or getattr(current_user, 'username', 'Sistema')
                except:
                    user_name = str(current_user) if current_user else 'Sistema'
        
        # Texto del encabezado con colores institucionales - sin iconos
        header_text = f"""
        <font color="#2E7D32"><b>Federación Mexicana de Radioexperimentadores A.C.</b></font><br/><br/>
        <font color="#1565C0" size="14"><b>Reporte de QSOs</b></font><br/><br/>
        <font color="#424242"><b>Fecha de Reportes:</b> {report_date}</font><br/><br/>
        <font color="#424242" size="9"><b>Generado el:</b> {generation_date}<br/>
        <b>Por:</b> {user_name}</font>
        """
        
        text_cell = Paragraph(header_text, self.styles['InstitutionalHeader'])
        
        # Crear tabla del encabezado con columnas ajustadas para logo original
        if logo_cell:
            header_table = Table([[logo_cell, text_cell]], colWidths=[2*inch, 5.5*inch])
        else:
            header_table = Table([[text_cell]], colWidths=[7.5*inch])
        
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo centrado
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),    # Texto a la izquierda
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, -1), self.colors['white']),
            ('BOX', (0, 0), (-1, -1), 1, self.colors['fmre_green']),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 15))
        
        # Línea separadora
        from reportlab.platypus import HRFlowable
        story.append(HRFlowable(width="100%", thickness=1, lineCap='round', color=colors.grey))
        story.append(Spacer(1, 15))
    
    def create_session_summary(self, stats, session_date=None):
        """Crea un resumen de sesión"""
        summary = {
            'fecha_sesion': session_date or datetime.now().date(),
            'total_participantes': stats.get('total_participants', 0),
            'total_reportes': stats.get('total_reports', 0),
            'participantes_por_region': {},
            'calidad_señal': {}
        }
        
        # Procesar participantes por región
        if 'by_region' in stats and not stats['by_region'].empty:
            for _, row in stats['by_region'].iterrows():
                summary['participantes_por_region'][row['region']] = row['count']
        
        # Procesar participantes por zona
        summary['participantes_por_zona'] = {}
        if 'by_zona' in stats and not stats['by_zona'].empty:
            for _, row in stats['by_zona'].iterrows():
                summary['participantes_por_zona'][row['zona']] = row['count']
        
        # Procesar participantes por sistema
        summary['participantes_por_sistema'] = {}
        if 'by_sistema' in stats and not stats['by_sistema'].empty:
            for _, row in stats['by_sistema'].iterrows():
                summary['participantes_por_sistema'][row['sistema']] = row['count']
        
        # Procesar calidad de señal
        if 'signal_quality' in stats and not stats['signal_quality'].empty:
            total_signals = stats['signal_quality']['count'].sum()
            for _, row in stats['signal_quality'].iterrows():
                quality_text = {1: 'Mala', 2: 'Regular', 3: 'Buena'}.get(row['signal_quality'], 'Desconocida')
                percentage = (row['count'] / total_signals * 100) if total_signals > 0 else 0
                summary['calidad_señal'][quality_text] = {
                    'cantidad': row['count'],
                    'porcentaje': round(percentage, 1)
                }
        
        return summary
    
    def get_download_link(self, data, filename, file_type='csv'):
        """Genera enlace de descarga para Streamlit"""
        if file_type == 'csv':
            mime_type = 'text/csv'
        elif file_type == 'xlsx':
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif file_type == 'pdf':
            mime_type = 'application/pdf'
        else:
            mime_type = 'application/octet-stream'
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        b64 = base64.b64encode(data).decode()
        return f'<a href="data:{mime_type};base64,{b64}" download="{filename}">Descargar {filename}</a>'
