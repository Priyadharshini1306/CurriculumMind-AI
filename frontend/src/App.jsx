import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import CourseLayout, { RequireReady } from './components/CourseLayout'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider, useAuth } from './hooks/useAuth'
import AdaptivePath from './pages/AdaptivePath'
import CourseHome from './pages/CourseHome'
import Courses from './pages/Courses'
import GraphDashboard from './pages/GraphDashboard'
import GraphReview from './pages/GraphReview'
import Home from './pages/Home'
import LearnerDashboard from './pages/LearnerDashboard'
import LearningPath from './pages/LearningPath'
import Login from './pages/Login'
import NewCourse from './pages/NewCourse'
import Overview from './pages/Overview'
import Quiz from './pages/Quiz'
import Register from './pages/Register'
import Resources from './pages/Resources'
import SequencingReview from './pages/SequencingReview'
import Verification1 from './pages/Verification1'

/** Logged-in users skip the landing, login and register pages. */
function PublicOnly({ children }) {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to="/app" replace /> : children
}

const ready = (el) => <RequireReady>{el}</RequireReady>

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<PublicOnly><Home /></PublicOnly>} />
          <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
          <Route path="/register" element={<PublicOnly><Register /></PublicOnly>} />

          <Route path="/app" element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route index element={<Courses />} />
            <Route path="new" element={<NewCourse />} />
            <Route path="course/:id" element={<CourseLayout />}>
              <Route index element={<CourseHome />} />
              {/* review gates: the learner approves each AI-made step */}
              <Route path="curriculum" element={<Verification1 />} />
              <Route path="map" element={<GraphReview />} />
              <Route path="plan" element={<SequencingReview />} />
              {/* learning, available once the course is set up */}
              <Route path="learn" element={ready(<LearningPath />)} />
              <Route path="quiz" element={ready(<Quiz />)} />
              <Route path="progress" element={ready(<LearnerDashboard />)} />
              <Route path="adaptive" element={ready(<AdaptivePath />)} />
              <Route path="explore" element={ready(<GraphDashboard />)} />
              <Route path="resources" element={ready(<Resources />)} />
              <Route path="overview" element={ready(<Overview />)} />
            </Route>
            <Route path="*" element={<Navigate to="/app" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
