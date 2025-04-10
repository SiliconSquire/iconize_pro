import os
import sys
import traceback
from io import BytesIO

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QProgressBar,
    QMessageBox,
    QLineEdit,
    QCheckBox,
    QSpacerItem,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QIcon

try:
    import qdarkstyle
except ImportError:
    qdarkstyle = None
    print("Warning: qdarkstyle not found. Using default theme.")
    print("Install with: pip install qdarkstyle")


try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    print("ERROR: Pillow library not found.")
    print("Please install it: pip install Pillow")
    sys.exit(1)

try:
    from cairosvg import svg2png
except ImportError:

    svg2png = None
    print("Warning: cairosvg library not found or its dependencies are missing.")
    print("SVG conversion will not be available.")
    print("Install with: pip install cairosvg")
    print("(Note: cairosvg may require external dependencies like GTK runtime)")
except Exception as e:
    svg2png = None
    print(f"Warning: Error importing cairosvg: {e}")
    print("SVG conversion might not work.")


PNG_ICON_SIZES = [16, 24, 32, 48, 64, 96, 128, 192, 256, 512]
ICO_ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
PNG_OUTPUT_FORMAT = "png"


class IconConversionWorker(QObject):
    """
    Worker object to perform icon/image conversion in a separate thread.
    """

    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    file_progress = pyqtSignal(int, int)
    finished = pyqtSignal(int, int, int)
    error = pyqtSignal(str)

    def __init__(self, image_files, base_output_folder, options):
        super().__init__()
        self.image_files = image_files
        self.base_output_folder = base_output_folder
        self.options = options
        self._is_running = True

    def stop(self):
        self.status_update.emit("Cancellation requested...")
        self._is_running = False

    def _convert_svg_to_png_worker(self, svg_path):
        if svg2png is None:
            self.status_update.emit(
                f"Skipping SVG (cairosvg not available): {os.path.basename(svg_path)}"
            )
            return None
        try:

            with open(svg_path, "rb") as f_in, BytesIO() as png_stream:
                svg2png(
                    file_obj=f_in,
                    write_to=png_stream,
                    output_width=1024,
                    output_height=1024,
                )
                png_stream.seek(0)
                with Image.open(png_stream) as img_svg:
                    return img_svg.convert("RGBA").copy()
        except FileNotFoundError:
            self.status_update.emit(
                f"Error: SVG file not found - {os.path.basename(svg_path)}"
            )
            return None
        except Exception as e:
            self.status_update.emit(
                f"Error converting SVG {os.path.basename(svg_path)}: {e}"
            )
            return None

    def run_conversion(self):
        if not self.image_files:
            self.error.emit("No images selected for processing.")
            self.finished.emit(0, 0, 0)
            return

        resized_output_folder = os.path.join(self.base_output_folder, "resized")
        ico_output_folder = os.path.join(self.base_output_folder, "ico")

        try:
            if self.options.get("do_png"):
                os.makedirs(resized_output_folder, exist_ok=True)
            if self.options.get("do_multi_ico") or self.options.get("do_single_ico"):
                os.makedirs(ico_output_folder, exist_ok=True)
        except OSError as e:
            self.error.emit(
                f"Could not create output subfolders in '{self.base_output_folder}': {e}"
            )
            self.finished.emit(0, 0, len(self.image_files))
            return

        num_images = len(self.image_files)
        processed_count = 0
        skipped_count = 0
        error_count = 0

        for i, image_path in enumerate(self.image_files):
            if not self._is_running:
                self.status_update.emit("Conversion cancelled.")
                break

            current_progress = int(((i + 1) / num_images) * 100)
            self.progress.emit(current_progress)
            self.file_progress.emit(i + 1, num_images)

            image_name, ext = os.path.splitext(os.path.basename(image_path))
            self.status_update.emit(
                f"Processing ({i+1}/{num_images}): {os.path.basename(image_path)}"
            )

            potential_multi_res_ico_path = os.path.join(
                ico_output_folder, f"{image_name}.ico"
            )
            if self.options.get("do_multi_ico") and os.path.exists(
                potential_multi_res_ico_path
            ):
                self.status_update.emit(
                    f"Skipping (Multi-res ICO exists): {os.path.basename(image_path)}"
                )
                skipped_count += 1
                continue

            img = None
            load_error = False
            try:
                if ext.lower() == ".svg":
                    if svg2png:
                        img = self._convert_svg_to_png_worker(image_path)
                        if img is None:
                            load_error = True
                    else:
                        self.status_update.emit(
                            f"Skipping SVG (cairosvg unavailable): {os.path.basename(image_path)}"
                        )
                        load_error = True
                elif ext.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"]:
                    with Image.open(image_path) as temp_img:
                        img = temp_img.convert("RGBA").copy()
                else:
                    self.status_update.emit(
                        f"Skipping unsupported type: {os.path.basename(image_path)}"
                    )
                    skipped_count += 1
                    continue
            except FileNotFoundError:
                self.status_update.emit(
                    f"Error: File not found - {os.path.basename(image_path)}"
                )
                load_error = True
            except UnidentifiedImageError:
                self.status_update.emit(
                    f"Error: Cannot identify image - {os.path.basename(image_path)}"
                )
                load_error = True
            except Exception as e:
                self.status_update.emit(
                    f"Error loading {os.path.basename(image_path)}: {e}"
                )
                load_error = True

            if load_error or img is None:
                error_count += 1
                continue

            png_paths_for_ico = {}
            step_error_occurred = False

            if self.options.get("do_png") and self._is_running:
                self.status_update.emit(f"Generating PNGs for: {image_name}")
                for size in PNG_ICON_SIZES:
                    if not self._is_running:
                        break
                    output_path = os.path.join(
                        resized_output_folder,
                        f"{image_name}_{size}.{PNG_OUTPUT_FORMAT}",
                    )
                    try:
                        with img.copy() as img_copy_png:
                            img_copy_png.thumbnail(
                                (size, size), Image.Resampling.LANCZOS
                            )
                            if img_copy_png.width > 0 and img_copy_png.height > 0:
                                img_copy_png.save(
                                    output_path, format=PNG_OUTPUT_FORMAT.upper()
                                )

                                if (
                                    self.options.get("do_single_ico")
                                    and size in ICO_ICON_SIZES
                                ):
                                    png_paths_for_ico[size] = output_path
                            else:
                                self.status_update.emit(
                                    f"Warning: Skipped saving empty PNG for size {size}"
                                )
                    except Exception as e:
                        self.status_update.emit(
                            f"Error saving PNG {size} for {image_name}: {e}"
                        )
                        step_error_occurred = True

            if self.options.get("do_multi_ico") and self._is_running:
                self.status_update.emit(f"Generating packed ICO for: {image_name}")
                ico_sizes_tuples = [(s, s) for s in ICO_ICON_SIZES]
                try:
                    img.save(
                        potential_multi_res_ico_path,
                        format="ICO",
                        sizes=ico_sizes_tuples,
                    )
                except Exception as e:
                    self.status_update.emit(
                        f"Error saving multi-res ICO for {image_name}: {e}"
                    )
                    step_error_occurred = True

            if self.options.get("do_single_ico") and self._is_running:
                self.status_update.emit(f"Generating single ICOs for: {image_name}")
                if not self.options.get("do_png"):
                    self.status_update.emit(
                        f"Warning: Cannot create single ICOs for {image_name} as PNG generation was disabled."
                    )
                elif not png_paths_for_ico:
                    self.status_update.emit(
                        f"Warning: No suitable PNGs found/created for single ICOs ({image_name})."
                    )
                else:
                    for size in ICO_ICON_SIZES:
                        if not self._is_running:
                            break
                        single_ico_output_path = os.path.join(
                            ico_output_folder, f"{image_name}_{size}.ico"
                        )
                        source_png_path = png_paths_for_ico.get(size)

                        if source_png_path and os.path.exists(source_png_path):
                            try:
                                with Image.open(source_png_path) as png_image:
                                    png_image.save(single_ico_output_path, format="ICO")
                            except Exception as e:
                                self.status_update.emit(
                                    f"Error saving single ICO {size} for {image_name}: {e}"
                                )
                                step_error_occurred = True
                        elif source_png_path:
                            self.status_update.emit(
                                f"Warning: Source PNG missing for single ICO {size} ({image_name})"
                            )

            if not step_error_occurred:
                processed_count += 1
            else:
                error_count += 1
            if isinstance(img, Image.Image):
                try:
                    img.close()
                except Exception:
                    pass

        if self._is_running:
            self.progress.emit(100)
            final_msg = f"Finished: {processed_count} processed, {skipped_count} skipped, {error_count} errors."
            self.status_update.emit(final_msg)

        self.finished.emit(processed_count, skipped_count, error_count)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Icon & Image Processor")
        self.setGeometry(100, 100, 650, 550)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.image_files = []

        self.base_output_folder = os.path.join(
            os.path.expanduser("~"), "processed_images"
        )
        self.conversion_thread = None
        self.conversion_worker = None

        icon_path = os.path.join(self.base_dir, "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"Warning: Icon file not found at '{icon_path}'")

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.image_label = QLabel(
            "Drag & drop images (SVG, PNG, JPG...) here\nor click 'Select Images'", self
        )
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setWordWrap(True)
        self.image_label.setStyleSheet(
            "QLabel { border: 2px dashed gray; padding: 20px; min-height: 80px; }"
        )
        main_layout.addWidget(self.image_label)
        self.setAcceptDrops(True)

        select_buttons_layout = QHBoxLayout()
        self.select_button = QPushButton("Select Images", self)
        select_buttons_layout.addWidget(self.select_button)
        self.clear_button = QPushButton("Clear Selection", self)
        select_buttons_layout.addWidget(self.clear_button)
        main_layout.addLayout(select_buttons_layout)

        output_layout = QHBoxLayout()
        self.select_output_button = QPushButton("Select Base Output Folder", self)
        output_layout.addWidget(self.select_output_button)
        self.output_path_display = QLineEdit(self)
        self.output_path_display.setText(os.path.abspath(self.base_output_folder))
        self.output_path_display.setReadOnly(True)
        output_layout.addWidget(self.output_path_display)
        main_layout.addLayout(output_layout)

        options_layout = QVBoxLayout()
        options_layout.addWidget(QLabel("Processing Options:", self))

        self.cb_generate_pngs = QCheckBox("Generate Resized PNGs (16px - 512px)", self)
        self.cb_generate_pngs.setChecked(True)
        options_layout.addWidget(self.cb_generate_pngs)

        self.cb_generate_multi_ico = QCheckBox(
            "Generate Multi-Resolution ICO (Packed, 16px - 256px)", self
        )
        self.cb_generate_multi_ico.setChecked(True)
        options_layout.addWidget(self.cb_generate_multi_ico)

        self.cb_generate_single_icos = QCheckBox(
            "Generate Single-Resolution ICOs (from PNGs, 16px - 256px)", self
        )
        self.cb_generate_single_icos.setChecked(True)
        options_layout.addWidget(self.cb_generate_single_icos)

        main_layout.addLayout(options_layout)

        main_layout.addSpacerItem(
            QSpacerItem(
                20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
            )
        )

        self.process_button = QPushButton("Start Processing", self)
        self.process_button.setEnabled(False)
        self.process_button.setStyleSheet(
            "QPushButton { padding: 10px; font-weight: bold; }"
        )
        main_layout.addWidget(self.process_button)

        self.status_label = QLabel("Ready. Select images and choose options.", self)
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% (%v/%m files)")
        main_layout.addWidget(self.progress_bar)

        self.select_button.clicked.connect(self.select_images)
        self.clear_button.clicked.connect(self.clear_selection)
        self.select_output_button.clicked.connect(self.select_output_directory)
        self.process_button.clicked.connect(self.start_processing)

        self.cb_generate_pngs.stateChanged.connect(self.update_options_logic)

        self.update_ui_after_selection()
        self.update_options_logic()

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()

        if mime_data.hasUrls() and all(url.isLocalFile() for url in mime_data.urls()):
            supported_extensions = (
                ".png",
                ".webp",
                ".jpg",
                ".jpeg",
                ".bmp",
                ".gif",
                ".tiff",
                ".svg",
            )
            if any(
                url.toLocalFile().lower().endswith(supported_extensions)
                for url in mime_data.urls()
            ):
                event.acceptProposedAction()
                self.image_label.setStyleSheet(
                    "QLabel { border: 2px solid lightgreen; padding: 20px; min-height: 80px; }"
                )
            else:
                event.ignore()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):

        self.image_label.setStyleSheet(
            "QLabel { border: 2px dashed gray; padding: 20px; min-height: 80px; }"
        )

    def dropEvent(self, event):
        valid_files = []
        supported_extensions = (
            ".png",
            ".webp",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".gif",
            ".tiff",
            ".svg",
        )
        for url in event.mimeData().urls():
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(supported_extensions):
                    valid_files.append(file_path)

        self.image_label.setStyleSheet(
            "QLabel { border: 2px dashed gray; padding: 20px; min-height: 80px; }"
        )

        if valid_files:
            current_files = set(self.image_files)
            new_files = set(valid_files)
            self.image_files = sorted(list(current_files.union(new_files)))
            self.update_ui_after_selection()
        else:
            self.status_label.setText("Drop contained no supported image files.")
            event.ignore()

    def select_images(self):

        filter_string = (
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tiff *.svg);;All Files (*)"
        )

        start_dir = os.path.expanduser("~")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Images", start_dir, filter_string
        )
        if files:
            current_files = set(self.image_files)
            new_files = set(files)
            self.image_files = sorted(list(current_files.union(new_files)))
            self.update_ui_after_selection()

    def clear_selection(self):
        self.image_files.clear()
        self.update_ui_after_selection()
        self.status_label.setText("Selection cleared. Ready.")

    def select_output_directory(self):
        start_dir = (
            self.base_output_folder
            if os.path.isdir(self.base_output_folder)
            else os.path.expanduser("~")
        )
        directory = QFileDialog.getExistingDirectory(
            self, "Select Base Output Folder", start_dir
        )
        if directory:
            self.base_output_folder = directory
            self.output_path_display.setText(os.path.abspath(self.base_output_folder))
            self.update_ui_after_selection()
            self.status_label.setText(
                f"Output folder set to: {self.base_output_folder}"
            )

    def update_ui_after_selection(self):
        """Updates UI based on whether files are selected."""
        num_files = len(self.image_files)
        abs_output_path = os.path.abspath(self.base_output_folder)
        self.output_path_display.setText(abs_output_path)

        if num_files > 0:
            self.image_label.setText(
                f"{num_files} image(s) selected.\n"
                f"Output will be saved in subfolders within:\n'{abs_output_path}'"
            )
            self.process_button.setEnabled(True)
            self.status_label.setText(f"{num_files} image(s) loaded. Ready to process.")
        else:
            self.image_label.setText(
                "Drag & drop images (SVG, PNG, JPG...) here\nor click 'Select Images'"
            )
            self.process_button.setEnabled(False)

            if self.status_label.text() not in ["Selection cleared. Ready."]:
                self.status_label.setText("Ready. Select images and choose options.")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(num_files if num_files > 0 else 100)
        self.progress_bar.setFormat(
            "%p%" + (f" (%v/{num_files} files)" if num_files > 0 else "")
        )

    def update_options_logic(self):
        """Ensure single-res ICO is disabled if PNG generation is disabled."""
        if not self.cb_generate_pngs.isChecked():
            self.cb_generate_single_icos.setChecked(False)
            self.cb_generate_single_icos.setEnabled(False)
            self.cb_generate_single_icos.setToolTip(
                "Requires 'Generate Resized PNGs' to be enabled."
            )
        else:
            self.cb_generate_single_icos.setEnabled(True)
            self.cb_generate_single_icos.setToolTip("")

    def set_controls_enabled(self, enabled):
        """Enable/disable controls during processing."""
        self.select_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.select_output_button.setEnabled(enabled)
        self.process_button.setEnabled(enabled and bool(self.image_files))
        self.cb_generate_pngs.setEnabled(enabled)

        self.cb_generate_single_icos.setEnabled(
            enabled and self.cb_generate_pngs.isChecked()
        )
        self.cb_generate_multi_ico.setEnabled(enabled)
        self.setAcceptDrops(enabled)

    def start_processing(self):
        if not self.image_files:
            QMessageBox.warning(
                self, "No Images", "Please select or drop image files first."
            )
            return

        if self.conversion_thread is not None and self.conversion_thread.isRunning():
            QMessageBox.information(self, "Busy", "Processing is already in progress.")
            return

        options = {
            "do_png": self.cb_generate_pngs.isChecked(),
            "do_multi_ico": self.cb_generate_multi_ico.isChecked(),
            "do_single_ico": self.cb_generate_single_icos.isChecked(),
        }

        if not any(options.values()):
            QMessageBox.warning(
                self, "No Options", "Please select at least one processing option."
            )
            return

        has_svg = any(f.lower().endswith(".svg") for f in self.image_files)
        if has_svg and svg2png is None:
            reply = QMessageBox.warning(
                self,
                "SVG Warning",
                "SVG files selected, but cairosvg library is missing or failed to load.\n"
                "SVG files will be skipped. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return

        self.conversion_thread = QThread(self)
        self.conversion_worker = IconConversionWorker(
            image_files=list(self.image_files),
            base_output_folder=self.base_output_folder,
            options=options,
        )
        self.conversion_worker.moveToThread(self.conversion_thread)

        self.conversion_worker.progress.connect(self.update_progress_percent)
        self.conversion_worker.status_update.connect(self.update_status)
        self.conversion_worker.file_progress.connect(self.update_progress_files)
        self.conversion_worker.finished.connect(self.processing_finished)
        self.conversion_worker.error.connect(self.processing_error)

        self.conversion_thread.started.connect(self.conversion_worker.run_conversion)
        self.conversion_worker.finished.connect(self.conversion_thread.quit)

        self.conversion_worker.finished.connect(self.conversion_worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)

        self.conversion_thread.finished.connect(self._clear_thread_ref)

        self.set_controls_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(self.image_files))
        self.status_label.setText("Starting processing...")
        self.conversion_thread.start()

    def _clear_thread_ref(self):
        """Slot to clear thread/worker references after thread finishes."""
        self.conversion_thread = None
        self.conversion_worker = None
        print("Thread and worker references cleared.")

    def update_progress_percent(self, value):

        pass

    def update_progress_files(self, current_file, total_files):
        self.progress_bar.setMaximum(total_files)
        self.progress_bar.setValue(current_file)

    def update_status(self, message):
        self.status_label.setText(message)
        QApplication.processEvents()

    def processing_error(self, message):
        QMessageBox.critical(self, "Processing Error", message)
        self.status_label.setText(f"Error: {message}")
        self.set_controls_enabled(True)
        self.progress_bar.setValue(0)
        self._clear_thread_ref()

    def processing_finished(self, processed, skipped, errors):
        final_output_path = os.path.abspath(self.base_output_folder)
        summary = (
            f"Processing complete.\n\n"
            f"Files Processed Successfully: {processed}\n"
            f"Files Skipped: {skipped}\n"
            f"Files with Errors: {errors}\n\n"
            f"Output saved relative to:\n'{final_output_path}'"
        )
        self.status_label.setText(
            f"Finished: {processed} processed, {skipped} skipped, {errors} errors."
        )
        QMessageBox.information(self, "Processing Complete", summary)
        self.set_controls_enabled(True)

    def closeEvent(self, event):
        if self.conversion_thread is not None and self.conversion_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "Processing is in progress. Cancel and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self.conversion_worker:
                    self.conversion_worker.stop()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == "__main__":

    if "Image" not in globals():
        QMessageBox.critical(
            None,
            "Missing Library",
            "Pillow library is required but not found.\nPlease install it: pip install Pillow",
        )
        sys.exit(1)

    app = QApplication(sys.argv)

    if qdarkstyle:
        try:
            app.setStyleSheet(qdarkstyle.load_stylesheet())
        except Exception as e:
            print(f"Warning: Failed to apply dark theme: {e}")
    else:
        pass

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
