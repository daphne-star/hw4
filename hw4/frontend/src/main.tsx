import {createRoot} from 'react-dom/client';
import {BrowserRouter,Routes,Route} from 'react-router-dom';
import {Layout,Home,About,Products,ProductPage} from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(<BrowserRouter><Routes><Route element={<Layout/>}><Route path="/" element={<Home/>}/><Route path="/products" element={<Products/>}/><Route path="/about" element={<About/>}/><Route path="/product/:id" element={<ProductPage/>}/></Route></Routes></BrowserRouter>);
