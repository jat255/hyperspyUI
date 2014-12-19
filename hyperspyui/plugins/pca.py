# -*- coding: utf-8 -*-
"""
Created on Fri Dec 12 23:44:01 2014

@author: Vidar Tonaas Fauske
"""


import plugin

import psutil, gc
import numpy as np

from python_qt_binding import QtGui, QtCore
from QtCore import *
from QtGui import *

from hyperspyui.util import win2sig, fig2win, Namespace
from hyperspyui.threaded import ProgressThreaded

def tr(text):
    return QCoreApplication.translate("PCA", text)

class PCA_Plugin(plugin.Plugin):
    def create_actions(self):
        self.ui.add_action('pca', "PCA", self.pca,
                        icon='pca.svg',
                        tip="Run Principal Component Analysis",
                        selection_callback=self.selection_rules)
        self.ui.add_action('pca_explore_components', "Explore PCA components",
                           self.explore_components,
                           selection_callback=self.selection_rules)
    
    def create_menu(self):
        self.ui.signalmenu.addAction(self.ui.actions['pca'])
        self.ui.signalmenu.addAction(self.ui.actions['pca_explore_components'])
    
    def create_toolbars(self):
        self.ui.add_toolbar_button("Signal", self.ui.actions['pca'])
                  
    # --- Add PCA action ---
    def selection_rules(self, win, action):
        s = win2sig(win, self.ui.signals)
        if s is None or s.signal.data.ndim <= 1:
            action.setEnabled(False)
        else:
            action.setEnabled(True)
            
            
    def _get_signal(self, signal):
        if signal is None:
            signal = self.ui.get_selected_signal()
        s = signal.signal

        if s.data.dtype.char not in ['e', 'f', 'd']:  # If not float        
            mb = QMessageBox(QMessageBox.Information, tr("Convert or copy"), 
                             tr("Signal data has the wrong data type (float " + 
                             "needed). Would you like to convert the current" +
                             " signal, or perform the decomposition on a " +
                             "copy?"))
            convert = mb.addButton(tr("Convert"), QMessageBox.AcceptRole)
            copy = mb.addButton(tr("Copy"), QMessageBox.RejectRole)
            mb.addButton(QMessageBox.Cancel)
            mb.exec_()
            btn = mb.clickedButton()
            if btn not in (convert, copy):
                return
            elif btn == copy: 
                new_s = s.deepcopy()
                if s.data.ndim == 2:
                    bk_s_navigate = self.nav_dim_backups[s]
                    s.axes_manager._set_axis_attribute_values('navigate', 
                                                              bk_s_navigate)
                s = new_s
                self.ui.add_signal_figure(s, signal.name + "[float]")
            s.change_dtype(float)
        return s, signal
            
    def _do_decomposition(self, s, force=False):
        if s.data.ndim == 2:
            bk_s_navigate = \
                    s.axes_manager._get_axis_attribute_values('navigate')
            s.axes_manager.set_signal_dimension(1)
        
        if force or s.learning_results.explained_variance_ratio is None:
            s.decomposition()
        
        if s.data.ndim == 2:
            s.axes_manager._set_axis_attribute_values('navigate', 
                                                      bk_s_navigate)
        return s
 
            
    def explore_components(self, signal=None, lazy="auto", n_component=50):
        ns = Namespace()
        ns.s, signal = self._get_signal(signal)
        
        if lazy == "auto":
            gc.collect()
            res_size = ns.s.data.nbytes * 2*n_component
            free_mem = psutil.phymem_usage()[2]
            lazy = res_size > free_mem
                
        def setup_lazy():
            ns.s = self._do_decomposition(ns.s)
            ns.s_scree = ns.s.get_decomposition_model(0)
            ns.s_residual = ns.s_scree - ns.s
            
        def lazy_setup_complete():
            ns.sw_scree, ns.sw_residual, ns.sw_factors, ns.sw_loadings = \
                make_compound(ns.s_scree, ns.s_residual)
            del ns.s_scree, ns.s_residual
            
            
        def fetch_lazy(*args, **kwargs):
            slicer = ns.s_lazynav.axes_manager._getitem_tuple_nav_sliced[0]
            if isinstance(slicer, slice):
                components = range(slicer[1])[slicer]
                ns.sw_factors.signal.axes_manager[0].slice = slicer
                ns.sw_loadings.signal.axes_manager[0].slice = slicer
            else:
                components = slicer
                ns.sw_factors.signal.axes_manager[0].index = slicer
                ns.sw_loadings.signal.axes_manager[0].index = slicer
            s = ns.s
            ns.sw_scree.signal.data = s.get_decomposition_model(components).data
            ns.sw_residual.signal.data = ns.sw_scree.signal.data - s.data
            self.ui.setUpdatesEnabled(False)
            try:
                ns.sw_scree.replot()
                ns.sw_residual.replot()
            finally:
                self.ui.setUpdatesEnabled(True)    # Continue updating UI
            
        def make_compound(s_scree, s_residual):
            s = ns.s
            s_scree.metadata.General.title = signal.name + " Component model"
            sw_scree = self.ui.add_signal_figure(s_scree, name = signal.name + 
                                           "[Component model]", plot=False)
                                           
            s_residual.metadata.General.title = signal.name + " Residual"
            sw_residual = self.ui.add_signal_figure(s_residual, name = signal.name + 
                                           "[Residual]", plot=False)
            if s.data.ndim == 2:
                bk_s_navigate = \
                        s.axes_manager._get_axis_attribute_values('navigate')
                s.axes_manager.set_signal_dimension(1)
            
            s_factors = s.get_decomposition_factors()
            sw_factors = self.ui.add_signal_figure(s_factors, 
                                           name = signal.name + "[Factor]",
                                           plot=False)
                
            s_loadings = s.get_decomposition_loadings()
            sw_loadings = self.ui.add_signal_figure(s_loadings, 
                                            name = signal.name + "[Loading]", 
                                            plot=False)
                                               
            if s.data.ndim == 2:
                s.axes_manager._set_axis_attribute_values('navigate', 
                                                          bk_s_navigate)
            
            if not lazy:
                # Set navigating axes common for all signals
                ax = s_scree.axes_manager['Principal component index']
                s_residual.axes_manager._axes[ax.index_in_array] = ax
                s_factors.axes_manager._axes[0] = ax
                s_loadings.axes_manager._axes[0] = ax
            else:
                for ax in s_scree.axes_manager.navigation_axes:
                    s_residual.axes_manager._axes[ax.index_in_array] = ax
                    
            
            
            # Make navigator signal
            if s.axes_manager.navigation_dimension == 0 or lazy:
                s_nav = s.get_explained_variance_ratio()
                s_nav.axes_manager[0].name = "Explained variance ratio"
                if n_component < s_nav.axes_manager[-1].size:
                    s_nav = s_nav.isig[1:n_component]
            else:
                s_nav = "auto"
                
            if lazy:
                s_nav2 = s_nav
                s_nav = "auto"
                s_nav2.axes_manager.set_signal_dimension(0)
                s_nav2.axes_manager.connect(fetch_lazy)
                self.ui.add_signal_figure(s_nav2,
                                    name = signal.name + "Component Navigator",
                                    plot=True)
                ns.s_lazynav = s_nav2
            
            # Plot signals with common navigator
            sw_scree.plot(navigator=s_nav)
            if s.axes_manager.navigation_dimension == 0:
                nax = s_scree._plot.navigator_plot.ax
                nax.set_ylabel("Explained variance ratio")
                nax.semilogy()
            
            sw_residual.plot(navigator=None)
            sw_factors.plot(navigator=None)
            sw_loadings.plot(navigator=None)
            return sw_scree, sw_residual, sw_factors, sw_loadings
        
        def threaded_gen():
            ns.s = self._do_decomposition(ns.s)
            ns.screedata = np.zeros((n_component-1,) + ns.s.data.shape,
                                    dtype=ns.s.data.dtype)
            for n in xrange(1, n_component):
                m = ns.s.get_decomposition_model(n)
                ns.screedata[n-1,...] = m.data
                del m.data
                del m
                yield n
            
        def on_threaded_complete():
            axes = []
            s = ns.s
            new_axis = {
                'name': 'Principal component index',
                'size': n_component-1,
                'units': '',
                'navigate': True}
            axes.append(new_axis)
            axes.extend(s.axes_manager._get_axes_dicts())


            s_scree = s.__class__(
                ns.screedata,
                axes=axes,
                metadata=s.metadata.as_dictionary(),)
            ns.screedata = None
            s_residual = s_scree.deepcopy()
            s_residual.data -= s.data
                    
            make_compound(s_scree, s_residual)
        
        if lazy:
            f = setup_lazy
            c = lazy_setup_complete
        else:
            f = threaded_gen()
            c = on_threaded_complete
        t = ProgressThreaded(self.ui, f, c, 
                             label='Performing PCA',
                             cancellable=not lazy,
                             generator_N=n_component-1)
        t.run()
        

    def pca(self, signal=None):
        ns = Namespace()
        ns.s, signal = self._get_signal(signal)
        
        def do_threaded():
            ns.s = self._do_decomposition(ns.s)
            
        def on_complete():
            ax = ns.s.plot_explained_variance_ratio()
                
            # Clean up plot and present, allow user to select components by picker
            ax.set_title("")
            scree = ax.get_figure().canvas
            scree.draw()
            scree.setWindowTitle("Pick number of components")
            def clicked(event):
                components = round(event.xdata)
                # Num comp. picked, perform PCA, wrap new signal and plot
                sc = ns.s.get_decomposition_model(components)
                self.ui.add_signal_figure(sc, signal.name + "[PCA]")
                # Close scree plot
                w = fig2win(scree.figure, self.ui.figures)
                w.close()
            scree.mpl_connect('button_press_event', clicked)
            
        t = ProgressThreaded(self.ui, do_threaded, on_complete, 
                             label="Performing PCA")
        t.run()
        
                        
                        
        
        